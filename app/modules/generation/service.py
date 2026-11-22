"""Sinh câu hỏi từ tài liệu (lõi của hệ thống).

Quy trình mỗi chunk: dựng ngữ cảnh -> LLM sinh -> kiểm bằng luật -> LLM kiểm định -> loại trùng -> lưu.
Câu không đạt vẫn được lưu với status="rejected" và lý do để đo chất lượng.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Chunk, Question
from app.modules.embedding.base import Embedder
from app.modules.generation.prompts import build_generate_prompt
from app.modules.generation.rules import check_question, ensure_rubric, finalize
from app.modules.generation.schemas import RawQuestion, Spec, default_specs
from app.modules.generation.validator import llm_validate_batch
from app.modules.ingestion.service import chunk_embedding_text
from app.modules.llm.base import LLMError, LLMProvider, LLMRateLimited
from app.modules.vectorstore.numpy_store import NumpyVectorStore

log = logging.getLogger(__name__)

# Lý do loại khi câu mới giống câu đã có. Đây không phải lỗi chất lượng nên báo cáo đánh giá tách riêng (xem evaluation/runner.py).
DUPLICATE_REASON = "trùng với câu hỏi đã có"


@dataclass
class GenerationReport:
    """Kết quả một lần sinh: câu hợp lệ, câu bị loại, và lỗi (LLM lỗi, sai định dạng)."""

    created: list[Question] = field(default_factory=list)
    rejected: list[Question] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rate_limited: bool = False  # True nếu dừng giữa chừng vì hết hạn mức gọi LLM (chạy lại sau sẽ làm tiếp)


class GenerationService:
    """RAG theo chiều ngược: lấy chunk (+ chunk liên quan) -> LLM sinh câu hỏi -> kiểm tra -> lưu."""

    def __init__(self, settings: Settings, llm: LLMProvider, embedder: Embedder, store: NumpyVectorStore):
        self.s = settings
        self.llm = llm
        self.embedder = embedder
        self.store = store

    # ---- ngữ cảnh -------------------------------------------------------------------------
    def build_context(self, db: Session, chunk: Chunk, with_neighbors: bool) -> tuple[str, list[int]]:
        """Ngữ cảnh = chunk gốc (+ các chunk gần nghĩa nhất CÙNG tài liệu nếu with_neighbors). Trả về (văn bản, danh sách id chunk)."""
        parts = [self._fmt(chunk)]
        ids = [chunk.id]
        if with_neighbors and self.s.retrieval_top_k > 0:
            same_doc = set(db.scalars(select(Chunk.id).where(Chunk.document_id == chunk.document_id)))
            qv = self.embedder.embed([chunk_embedding_text(chunk.heading, chunk.text)])[0]
            for cid, _score in self.store.search(qv, self.s.retrieval_top_k, allowed_ids=same_doc, exclude_ids={chunk.id}):
                nb = db.get(Chunk, cid)
                if nb:
                    parts.append(self._fmt(nb))
                    ids.append(cid)
        return "\n\n---\n\n".join(parts), ids

    @staticmethod
    def _fmt(c: Chunk) -> str:
        return f"[Mục: {c.heading}]\n{c.text}" if c.heading else c.text

    # ---- sinh câu hỏi -----------------------------------------------------------------------
    def generate_for_chunk(
        self, db: Session, chunk: Chunk, specs: list[Spec] | None = None, use_rag_context: bool = True, dedupe: bool = True,
        only_missing: bool = False,
    ) -> GenerationReport:
        """only_missing=True: bỏ qua yêu cầu (loại, mức) mà chunk đã đủ câu hợp lệ -> chạy lại sau lỗi không tốn thêm lượt gọi LLM."""
        report = GenerationReport()
        specs = specs or default_specs()
        if only_missing:
            rows = db.execute(
                select(Question.qtype, Question.level).where(Question.chunk_id == chunk.id, Question.status == "valid")
            ).all()
            have = Counter((r[0], r[1]) for r in rows)
            specs = [sp for sp in specs if have[(sp.qtype, sp.level)] < sp.count]
        # Mỗi mức một lượt gọi LLM. Mức "apply" cần thêm chunk lân cận để dựng tình huống nhiều bước.
        for level in ("recall", "apply"):
            lvl_specs = [sp for sp in specs if sp.level == level]
            if not lvl_specs:
                continue
            # judge_ctx: ngữ cảnh dùng để KIỂM TRA câu hỏi; prompt_ctx: ngữ cảnh đưa cho LLM khi sinh.
            judge_ctx, ctx_ids = self.build_context(db, chunk, with_neighbors=(level == "apply"))
            # baseline "không RAG" (dùng cho đánh giá): LLM chỉ thấy tên chủ đề, nhưng vẫn bị kiểm tra theo tài liệu thật
            prompt_ctx = judge_ctx if use_rag_context else f"[Mục: {chunk.heading or chunk.document.title}]"
            self._run(db, chunk, prompt_ctx, judge_ctx, ctx_ids, lvl_specs, report, dedupe)
            if report.rate_limited:  # đã hết hạn mức: gọi tiếp chỉ tốn thời gian
                break
        db.commit()
        return report

    def _run(self, db, chunk, prompt_ctx, context, ctx_ids, specs, report: GenerationReport, dedupe: bool = True) -> None:
        """Một lượt: gọi LLM, kiểm từng câu, lưu vào `db` (chưa commit) và ghi vào `report`."""
        system, user = build_generate_prompt(chunk.heading, prompt_ctx, specs)
        try:
            data = self.llm.complete_json(system, user, temperature=0.4)
        except LLMError as e:
            report.errors.append(str(e))
            report.rate_limited = isinstance(e, LLMRateLimited)
            return
        # LLM có thể trả {"questions": [...]} hoặc trực tiếp một danh sách.
        items = data.get("questions") if isinstance(data, dict) else data
        if not isinstance(items, list):
            report.errors.append("LLM không trả về danh sách questions")
            return

        existing = (
            [q.question for q in db.scalars(select(Question).where(Question.chunk_id == chunk.id, Question.status == "valid"))]
            if dedupe else []
        )
        # Bước 1: parse + kiểm bằng luật (miễn phí) cho cả lô. `pending` = câu qua luật, chờ LLM kiểm định.
        parsed: list[tuple[RawQuestion, str | None, dict | None]] = []  # (câu thô, lý do loại, bản đã chuẩn hoá)
        for item in items:
            try:
                raw = RawQuestion.model_validate(item)
            except Exception as e:  # pydantic ValidationError, item không phải dict...
                report.errors.append(f"item sai schema: {str(e)[:120]}")
                continue
            ensure_rubric(raw)
            reason = check_question(raw, context, self.s.reject_unverified_numbers)
            parsed.append((raw, reason, None if reason else finalize(raw)))

        # Bước 2: MỘT lần gọi LLM kiểm định cho cả lô (thay vì mỗi câu một lần).
        verdict: dict[int, tuple[bool, str]] = {}
        pending = [i for i, (_, reason, _) in enumerate(parsed) if not reason]
        if pending and self.s.validate_questions:
            try:
                res = llm_validate_batch(self.llm, context, [parsed[i][2] for i in pending])  # type: ignore[misc]
            except LLMRateLimited as e:
                report.errors.append(str(e))
                report.rate_limited = True
                db.flush()
                return  # chưa kiểm định thì không lưu câu nào của lô này; lô trước đó vẫn được giữ
            verdict = dict(zip(pending, res, strict=True))

        # Bước 3: loại trùng (cosine, cục bộ) rồi lưu: câu đạt -> valid, còn lại -> rejected kèm lý do.
        for i, (raw, reason, fin) in enumerate(parsed):
            if not reason and i in verdict:
                ok, why = verdict[i]
                reason = None if ok else why
            if not reason and dedupe and self._is_duplicate(raw.question, existing):
                reason = DUPLICATE_REASON

            if reason or fin is None:
                row = Question(
                    chunk_id=chunk.id, qtype=raw.qtype[:20], level=raw.level[:20], question=raw.question,
                    options=raw.options, answer=raw.answer, source_quote=raw.source_quote,
                    status="rejected", reject_reason=(reason or "")[:300], model=self.llm.model or self.llm.name,
                )
                db.add(row)
                report.rejected.append(row)
                continue

            fin["meta"]["context_chunk_ids"] = ctx_ids
            row = Question(chunk_id=chunk.id, status="valid", model=self.llm.model or self.llm.name, **fin)
            db.add(row)
            report.created.append(row)
            existing.append(raw.question)
        db.flush()

    def _is_duplicate(self, text: str, existing: list[str]) -> bool:
        """Trùng nếu cosine với câu đã có >= dedup_threshold (vector đã chuẩn hoá nên tích vô hướng = cosine)."""
        if not existing:
            return False
        vecs = self.embedder.embed([text, *existing])
        sims = vecs[1:] @ vecs[0]
        return bool(sims.max() >= self.s.dedup_threshold)

    def generate_for_document(self, db: Session, document_id: int, specs: list[Spec] | None = None) -> GenerationReport:
        total = GenerationReport()
        chunks = db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.position)).all()
        for c in chunks:
            r = self.generate_for_chunk(db, c, specs)
            total.created += r.created
            total.rejected += r.rejected
            total.errors += r.errors
            if r.rate_limited:
                total.rate_limited = True
                break
        return total

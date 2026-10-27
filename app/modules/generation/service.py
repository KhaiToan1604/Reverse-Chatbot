import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Chunk, Question
from app.modules.embedding.base import Embedder
from app.modules.generation.prompts import build_generate_prompt
from app.modules.generation.rules import check_question, finalize
from app.modules.generation.schemas import RawQuestion, Spec, default_specs
from app.modules.generation.validator import llm_validate
from app.modules.ingestion.service import chunk_embedding_text
from app.modules.llm.base import LLMError, LLMProvider
from app.modules.vectorstore.numpy_store import NumpyVectorStore

log = logging.getLogger(__name__)


@dataclass
class GenerationReport:
    created: list[Question] = field(default_factory=list)
    rejected: list[Question] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class GenerationService:
    """RAG theo chiều ngược: lấy chunk (+ chunk liên quan) -> LLM sinh câu hỏi -> kiểm tra -> lưu."""

    def __init__(self, settings: Settings, llm: LLMProvider, embedder: Embedder, store: NumpyVectorStore):
        self.s = settings
        self.llm = llm
        self.embedder = embedder
        self.store = store

    # ---- ngữ cảnh -------------------------------------------------------------------------
    def build_context(self, db: Session, chunk: Chunk, with_neighbors: bool) -> tuple[str, list[int]]:
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
        self, db: Session, chunk: Chunk, specs: list[Spec] | None = None, use_rag_context: bool = True, dedupe: bool = True
    ) -> GenerationReport:
        report = GenerationReport()
        specs = specs or default_specs()
        for level in ("recall", "apply"):
            lvl_specs = [sp for sp in specs if sp.level == level]
            if not lvl_specs:
                continue
            judge_ctx, ctx_ids = self.build_context(db, chunk, with_neighbors=(level == "apply"))
            # baseline "không RAG" (dùng cho đánh giá): LLM chỉ thấy tên chủ đề, nhưng vẫn bị kiểm tra theo tài liệu thật
            prompt_ctx = judge_ctx if use_rag_context else f"[Mục: {chunk.heading or chunk.document.title}]"
            self._run(db, chunk, prompt_ctx, judge_ctx, ctx_ids, lvl_specs, report, dedupe)
        db.commit()
        return report

    def _run(self, db, chunk, prompt_ctx, context, ctx_ids, specs, report: GenerationReport, dedupe: bool = True) -> None:
        system, user = build_generate_prompt(chunk.heading, prompt_ctx, specs)
        try:
            data = self.llm.complete_json(system, user, temperature=0.4)
        except LLMError as e:
            report.errors.append(str(e))
            return
        items = data.get("questions") if isinstance(data, dict) else data
        if not isinstance(items, list):
            report.errors.append("LLM không trả về danh sách questions")
            return

        existing = (
            [q.question for q in db.scalars(select(Question).where(Question.chunk_id == chunk.id, Question.status == "valid"))]
            if dedupe else []
        )
        for item in items:
            try:
                raw = RawQuestion.model_validate(item)
            except Exception as e:  # pydantic ValidationError, item không phải dict...
                report.errors.append(f"item sai schema: {str(e)[:120]}")
                continue

            reason = check_question(raw, context)
            fin = None
            if not reason:
                fin = finalize(raw)
                if self.s.validate_questions:
                    ok, why = llm_validate(self.llm, context, fin)
                    reason = None if ok else why
            if not reason and dedupe and self._is_duplicate(raw.question, existing):
                reason = "trùng với câu hỏi đã có"

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
        return total

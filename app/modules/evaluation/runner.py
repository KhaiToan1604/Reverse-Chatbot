"""Đánh giá hệ thống — phần quyết định điểm của đề tài.

1. question_quality_report : tỉ lệ câu hỏi qua kiểm tra tự động, lý do bị loại.
2. export/import review    : người thật duyệt mẫu câu hỏi -> tỉ lệ đạt do người đánh giá.
3. grader_agreement        : so điểm của hệ thống với điểm người chấm (MAE, accuracy, Cohen's kappa).
4. rag_vs_norag            : sinh câu hỏi CÓ tài liệu vs KHÔNG có tài liệu, đo tỉ lệ bịa/không có căn cứ.
"""

import csv
import json
import random
from collections import Counter
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Question
from app.modules.generation.schemas import Spec, default_specs
from app.modules.generation.service import GenerationService
from app.modules.grading.service import GradingService


def question_quality_report(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(Question)) or 0
    valid = db.scalar(select(func.count()).select_from(Question).where(Question.status == "valid")) or 0
    reasons = Counter(
        (r or "").split(":")[0][:80] for r in db.scalars(select(Question.reject_reason).where(Question.status == "rejected"))
    )
    by_type = {
        f"{t}/{lv}": n
        for t, lv, n in db.execute(
            select(Question.qtype, Question.level, func.count()).where(Question.status == "valid").group_by(Question.qtype, Question.level)
        )
    }
    return {
        "generated_total": total,
        "valid": valid,
        "rejected": total - valid,
        "auto_pass_rate": round(valid / total, 4) if total else None,
        "valid_by_type_level": by_type,
        "reject_reasons": dict(reasons.most_common()),
    }


# ---- duyệt thủ công -----------------------------------------------------------------------
def export_review_csv(db: Session, path: str, n: int = 50, seed: int = 0) -> int:
    qs = db.scalars(select(Question).where(Question.status == "valid")).all()
    random.Random(seed).shuffle(qs)
    qs = qs[:n]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["question_id", "qtype", "level", "question", "options", "answer", "source_quote", "human_ok(1/0)", "note"])
        for q in qs:
            w.writerow([q.id, q.qtype, q.level, q.question, json.dumps(q.options, ensure_ascii=False) if q.options else "",
                        q.answer, q.source_quote, "", ""])
    return len(qs)


def import_review_labels(path: str) -> dict:
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig")) if (r.get("human_ok(1/0)") or "").strip() in ("0", "1")]
    if not rows:
        return {"labeled": 0}
    ok = sum(r["human_ok(1/0)"].strip() == "1" for r in rows)
    by_type: dict[str, list[int]] = {}
    for r in rows:
        by_type.setdefault(f"{r['qtype']}/{r['level']}", []).append(int(r["human_ok(1/0)"]))
    return {
        "labeled": len(rows),
        "human_pass_rate": round(ok / len(rows), 4),
        "by_type_level": {k: round(sum(v) / len(v), 4) for k, v in by_type.items()},
    }


# ---- độ đồng thuận của người chấm ---------------------------------------------------------
def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def grader_agreement(db: Session, grader: GradingService, path: str, threshold: float) -> dict:
    """CSV cần cột: question_id, answer, human_score (0..1)."""
    sys_scores, human_scores = [], []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        q = db.get(Question, int(r["question_id"]))
        if not q:
            continue
        sys_scores.append(grader.grade(q, r["answer"]).score)
        human_scores.append(float(r["human_score"]))
    n = len(sys_scores)
    if not n:
        return {"n": 0}
    sp = [s >= threshold for s in sys_scores]
    hp = [h >= threshold for h in human_scores]
    return {
        "n": n,
        "mae": round(sum(abs(s - h) for s, h in zip(sys_scores, human_scores)) / n, 4),
        "pass_fail_accuracy": round(sum(x == y for x, y in zip(sp, hp)) / n, 4),
        "cohen_kappa": round(cohen_kappa(sp, hp), 4),
    }


# ---- RAG vs không RAG ---------------------------------------------------------------------
def rag_vs_norag(db: Session, gen: GenerationService, n_chunks: int = 10, seed: int = 0, specs: list[Spec] | None = None) -> dict:
    """Mỗi chunk sinh câu hỏi 2 cách. Cả hai đều bị kiểm tra theo tài liệu thật; câu hỏi tạm được xoá sau khi đo."""
    chunk_ids = list(db.scalars(select(Chunk.id)))
    random.Random(seed).shuffle(chunk_ids)
    out = {}
    for label, use_rag in (("rag", True), ("no_rag", False)):
        created = rejected = 0
        reasons: Counter = Counter()
        for cid in chunk_ids[:n_chunks]:
            chunk = db.get(Chunk, cid)
            rep = gen.generate_for_chunk(db, chunk, specs or default_specs(), use_rag_context=use_rag, dedupe=False)
            created += len(rep.created)
            rejected += len(rep.rejected)
            reasons.update((q.reject_reason or "").split(":")[0][:80] for q in rep.rejected)
            ids = [q.id for q in rep.created + rep.rejected]
            if ids:
                db.execute(delete(Question).where(Question.id.in_(ids)))
                db.commit()
        tot = created + rejected
        out[label] = {"generated": tot, "valid": created, "valid_rate": round(created / tot, 4) if tot else None,
                      "top_reject_reasons": dict(reasons.most_common(5))}
    return out

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_container, require_admin
from app.api.schemas import GenerateIn
from app.common.errors import NotFound
from app.container import Container
from app.db.base import get_db
from app.db.models import Chunk, Question
from app.modules.generation.schemas import Spec

router = APIRouter(prefix="/questions", tags=["questions"], dependencies=[Depends(require_admin)])


def _q_out(q: Question) -> dict:
    return {
        "id": q.id, "chunk_id": q.chunk_id, "qtype": q.qtype, "level": q.level, "question": q.question,
        "options": q.options, "answer": q.answer, "explanation": q.explanation, "rubric": q.rubric,
        "source_quote": q.source_quote, "status": q.status, "reject_reason": q.reject_reason, "model": q.model,
    }


@router.post("/generate")
def generate(body: GenerateIn, db: Session = Depends(get_db), c: Container = Depends(get_container)):
    """Sinh câu hỏi cho một chunk hoặc cả tài liệu (gọi LLM nên có thể mất vài chục giây)."""
    specs = None
    if body.specs:
        try:
            for sp in body.specs:
                sp.validate_values()
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        specs = [Spec(sp.qtype, sp.level, sp.count) for sp in body.specs]

    if body.chunk_id:
        chunk = db.get(Chunk, body.chunk_id)
        if not chunk:
            raise NotFound("Không tìm thấy chunk")
        rep = c.generation.generate_for_chunk(db, chunk, specs)
    elif body.document_id:
        rep = c.generation.generate_for_document(db, body.document_id, specs)
    else:
        raise HTTPException(422, "Cần document_id hoặc chunk_id")
    return {
        "created": len(rep.created), "rejected": len(rep.rejected), "errors": rep.errors,
        "rejected_reasons": [q.reject_reason for q in rep.rejected],
        "questions": [_q_out(q) for q in rep.created],
    }


@router.get("")
def list_questions(document_id: int | None = None, status: str = "valid", qtype: str | None = None,
                   level: str | None = None, limit: int = Query(50, le=500), offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(Question).where(Question.status == status)
    if document_id:
        stmt = stmt.join(Chunk, Question.chunk_id == Chunk.id).where(Chunk.document_id == document_id)
    if qtype:
        stmt = stmt.where(Question.qtype == qtype)
    if level:
        stmt = stmt.where(Question.level == level)
    return [_q_out(q) for q in db.scalars(stmt.order_by(Question.id).limit(limit).offset(offset))]


@router.get("/{question_id}")
def get_question(question_id: int, db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if not q:
        raise NotFound("Không tìm thấy câu hỏi")
    return _q_out(q)

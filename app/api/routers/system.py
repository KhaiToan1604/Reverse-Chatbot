from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_container, require_admin
from app.container import Container
from app.db.base import get_db
from app.db.models import Chunk, Document, Question
from app.modules.evaluation.runner import question_quality_report

router = APIRouter()


@router.get("/health", tags=["system"])
def health(db: Session = Depends(get_db), c: Container = Depends(get_container)):
    return {
        "status": "ok",
        "llm": {"provider": c.llm.name, "model": c.llm.model},
        "embedding": {"name": c.embedder.name, "dim": c.embedder.dim},
        "documents": db.scalar(select(func.count()).select_from(Document)),
        "chunks": db.scalar(select(func.count()).select_from(Chunk)),
        "valid_questions": db.scalar(select(func.count()).select_from(Question).where(Question.status == "valid")),
        "vectors": c.store.count(),
    }


@router.get("/evaluation/report", tags=["evaluation"], dependencies=[Depends(require_admin)])
def evaluation_report(db: Session = Depends(get_db)):
    return question_quality_report(db)

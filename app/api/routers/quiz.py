from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_container
from app.api.schemas import AnswerIn, SessionIn, UserIn
from app.common.errors import NotFound
from app.container import Container
from app.db.base import get_db
from app.db.models import Chunk, Document, Question, User

router = APIRouter(tags=["quiz"])


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db)):
    u = User(display_name=body.display_name.strip())
    db.add(u)
    db.commit()
    return {"id": u.id, "display_name": u.display_name}


@router.get("/users/{user_id}/progress")
def user_progress(user_id: int, document_id: int | None = None, db: Session = Depends(get_db), c: Container = Depends(get_container)):
    return c.quiz.user_progress(db, user_id, document_id)


@router.post("/quiz/sessions", status_code=201)
def start_session(body: SessionIn, db: Session = Depends(get_db), c: Container = Depends(get_container)):
    s = c.quiz.start_session(db, body.user_id, body.num_questions, body.document_id)
    return {"session_id": s.id, "num_questions": s.num_questions, "document_id": s.document_id}


@router.get("/quiz/sessions/{session_id}/next")
def next_question(session_id: int, db: Session = Depends(get_db), c: Container = Depends(get_container)):
    return c.quiz.next_question(db, session_id)


@router.post("/quiz/sessions/{session_id}/answer")
def answer(session_id: int, body: AnswerIn, db: Session = Depends(get_db), c: Container = Depends(get_container)):
    return c.quiz.submit_answer(db, session_id, body.question_id, body.answer)


@router.get("/quiz/sessions/{session_id}/summary")
def summary(session_id: int, db: Session = Depends(get_db), c: Container = Depends(get_container)):
    return c.quiz.summary(db, session_id)


@router.get("/catalog")
def catalog(db: Session = Depends(get_db)):
    """Danh mục tài liệu cho người học (công khai, không lộ nội dung/đáp án).

    has_questions = mọi mục của tài liệu đều đã có ít nhất một câu hỏi hợp lệ trong ngân hàng."""
    n_chunks = dict(db.execute(select(Chunk.document_id, func.count()).group_by(Chunk.document_id)).all())
    n_covered = dict(
        db.execute(
            select(Chunk.document_id, func.count(func.distinct(Chunk.id)))
            .join(Question, Question.chunk_id == Chunk.id).where(Question.status == "valid").group_by(Chunk.document_id)
        ).all()
    )
    return [
        {"id": d.id, "title": d.title, "num_topics": n_chunks.get(d.id, 0),
         "has_questions": n_chunks.get(d.id, 0) > 0 and n_covered.get(d.id, 0) == n_chunks.get(d.id, 0)}
        for d in db.scalars(select(Document).order_by(Document.id))
    ]

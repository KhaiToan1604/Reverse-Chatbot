from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import Conflict, NotFound
from app.config import Settings
from app.db.models import Attempt, Chunk, Document, Mastery, Question, QuizSession, User, utcnow
from app.modules.adaptive.mastery import apply_attempt
from app.modules.adaptive.selector import QuestionSelector
from app.modules.grading.service import GradingService


def public_question(db: Session, q: Question) -> dict:
    """Dạng câu hỏi gửi cho người học — KHÔNG chứa đáp án/rubric/căn cứ."""
    chunk = db.get(Chunk, q.chunk_id)
    doc = db.get(Document, chunk.document_id) if chunk else None
    return {
        "question_id": q.id,
        "qtype": q.qtype,
        "level": q.level,
        "question": q.question,
        "options": [f"{'ABCD'[i]}. {o}" for i, o in enumerate(q.options)] if q.options else None,
        "topic": chunk.heading if chunk else "",
        "document": doc.title if doc else "",
    }


class QuizService:
    def __init__(self, settings: Settings, selector: QuestionSelector, grader: GradingService):
        self.s = settings
        self.selector = selector
        self.grader = grader

    # ---- phiên -------------------------------------------------------------------------
    def start_session(self, db: Session, user_id: int, num_questions: int, document_id: int | None) -> QuizSession:
        if not db.get(User, user_id):
            raise NotFound("Không tìm thấy người dùng")
        if document_id and not db.get(Document, document_id):
            raise NotFound("Không tìm thấy tài liệu")
        sess = QuizSession(user_id=user_id, document_id=document_id, num_questions=num_questions)
        db.add(sess)
        db.commit()
        return sess

    def _get_session(self, db: Session, session_id: int) -> QuizSession:
        sess = db.get(QuizSession, session_id)
        if not sess:
            raise NotFound("Không tìm thấy phiên")
        return sess

    def _answered(self, db: Session, sess: QuizSession) -> int:
        return len(db.scalars(select(Attempt.id).where(Attempt.session_id == sess.id)).all())

    def _finish(self, db: Session, sess: QuizSession) -> None:
        sess.status = "finished"
        sess.current_question_id = None
        sess.finished_at = utcnow()
        db.commit()

    def next_question(self, db: Session, session_id: int) -> dict:
        sess = self._get_session(db, session_id)
        answered = self._answered(db, sess)
        if sess.status == "finished" or answered >= sess.num_questions:
            if sess.status != "finished":
                self._finish(db, sess)
            return {"done": True, "answered": answered, "total": sess.num_questions, "question": None}

        q = db.get(Question, sess.current_question_id) if sess.current_question_id else None
        if q is None:
            q = self.selector.pick(db, sess.user_id, sess)
            if q is None:
                raise Conflict("Chưa có câu hỏi phù hợp. Hãy nạp tài liệu và sinh câu hỏi trước.")
            sess.current_question_id = q.id
            db.commit()
        return {"done": False, "answered": answered, "total": sess.num_questions, "question": public_question(db, q)}

    def submit_answer(self, db: Session, session_id: int, question_id: int, answer: str) -> dict:
        sess = self._get_session(db, session_id)
        if sess.status == "finished":
            raise Conflict("Phiên đã kết thúc")
        if sess.current_question_id != question_id:
            raise Conflict("Câu hỏi này không phải câu hiện tại của phiên (hãy gọi /next trước)")
        q = db.get(Question, question_id)

        res = self.grader.grade(q, answer)
        db.add(Attempt(
            session_id=sess.id, user_id=sess.user_id, question_id=q.id, user_answer=answer, score=res.score,
            is_correct=res.is_correct, feedback=res.feedback, missing_points=res.missing_points, graded_by=res.graded_by,
        ))
        m = db.get(Mastery, (sess.user_id, q.chunk_id))
        if m is None:
            m = Mastery(user_id=sess.user_id, chunk_id=q.chunk_id, mastery=0.0, streak=0, correct_count=0, wrong_count=0)
            db.add(m)
        apply_attempt(m, res.score, utcnow(), self.s)
        sess.current_question_id = None
        db.flush()

        answered = self._answered(db, sess)
        finished = answered >= sess.num_questions
        if finished:
            self._finish(db, sess)
        else:
            db.commit()

        chunk = db.get(Chunk, q.chunk_id)
        ref = q.answer
        if q.qtype == "mcq" and q.options:
            ref = f"{q.answer}. {q.options['ABCD'.index(q.answer)]}"
        return {
            "score": res.score, "is_correct": res.is_correct, "feedback": res.feedback,
            "missing_points": res.missing_points, "graded_by": res.graded_by,
            "reference_answer": ref, "explanation": q.explanation, "source_quote": q.source_quote,
            "topic": chunk.heading if chunk else "", "mastery": m.mastery,
            "next_review_at": m.due_at.isoformat() if m.due_at else None,
            "answered": answered, "total": sess.num_questions, "session_finished": finished,
        }

    def summary(self, db: Session, session_id: int) -> dict:
        sess = self._get_session(db, session_id)
        rows = db.execute(
            select(Attempt, Question, Chunk).join(Question, Attempt.question_id == Question.id)
            .join(Chunk, Question.chunk_id == Chunk.id).where(Attempt.session_id == sess.id).order_by(Attempt.id)
        ).all()
        by_topic: dict[str, list[float]] = {}
        for a, _q, c in rows:
            by_topic.setdefault(c.heading or f"Chunk {c.id}", []).append(a.score)
        weak = sorted(((t, sum(v) / len(v)) for t, v in by_topic.items()), key=lambda x: x[1])
        n = len(rows)
        return {
            "session_id": sess.id, "status": sess.status, "answered": n, "total": sess.num_questions,
            "average_score": round(sum(a.score for a, _, _ in rows) / n, 4) if n else 0.0,
            "correct": sum(a.is_correct for a, _, _ in rows),
            "weak_topics": [{"topic": t, "avg_score": round(s, 4)} for t, s in weak if s < self.s.pass_threshold],
            "attempts": [
                {"question": q.question, "qtype": q.qtype, "level": q.level, "topic": c.heading, "your_answer": a.user_answer,
                 "score": a.score, "is_correct": a.is_correct, "feedback": a.feedback, "missing_points": a.missing_points or []}
                for a, q, c in rows
            ],
        }

    def user_progress(self, db: Session, user_id: int, document_id: int | None = None) -> dict:
        if not db.get(User, user_id):
            raise NotFound("Không tìm thấy người dùng")
        stmt = select(Chunk, Document).join(Document, Chunk.document_id == Document.id).order_by(Chunk.id)
        if document_id:
            stmt = stmt.where(Chunk.document_id == document_id)
        chunks = db.execute(stmt).all()
        ms = {m.chunk_id: m for m in db.scalars(select(Mastery).where(Mastery.user_id == user_id))}
        now = utcnow()
        topics, due = [], 0
        for c, d in chunks:
            m = ms.get(c.id)
            is_due = m is not None and (m.due_at is None or m.due_at <= now)
            due += is_due
            topics.append({
                "chunk_id": c.id, "document": d.title, "topic": c.heading, "mastery": m.mastery if m else 0.0,
                "streak": m.streak if m else 0, "correct": m.correct_count if m else 0, "wrong": m.wrong_count if m else 0,
                "seen": m is not None, "due": is_due, "due_at": m.due_at.isoformat() if m and m.due_at else None,
            })
        n = len(topics)
        return {
            "user_id": user_id, "overall_mastery": round(sum(t["mastery"] for t in topics) / n, 4) if n else 0.0,
            "topics_total": n, "topics_seen": sum(t["seen"] for t in topics), "topics_due": due, "topics": topics,
        }

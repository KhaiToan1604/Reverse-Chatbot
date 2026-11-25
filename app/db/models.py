"""Các bảng CSDL (7 bảng). Thêm cột: khai báo `Mapped[...]` vào lớp tương ứng, xem chú ý ở db/base.py::create_all. Quan hệ chính:

Document 1-n Chunk 1-n Question;  User 1-n QuizSession 1-n Attempt (mỗi lần trả lời một câu);
Mastery là (User, Chunk) -> mức nắm vững + lịch ôn.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    """Giờ UTC không kèm múi giờ (SQLite không lưu tzinfo), dùng nhất quán cho mọi cột thời gian."""
    return datetime.now(UTC).replace(tzinfo=None)


class Document(Base):
    """Một tài liệu nguồn đã nạp. `content_hash` duy nhất để nạp lại cùng nội dung thì không tạo trùng."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(500), default="")
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    """Một đoạn của tài liệu (đơn vị sinh câu hỏi và đơn vị theo dõi mức nắm vững). `position` là thứ tự trong tài liệu."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(300), default="")
    text: Mapped[str] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="chunks")
    questions: Mapped[list["Question"]] = relationship(back_populates="chunk", cascade="all, delete-orphan")


class Question(Base):
    """Câu hỏi đã sinh. Câu bị loại vẫn được lưu (status="rejected" + reject_reason) để đo chất lượng."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    qtype: Mapped[str] = mapped_column(String(20))  # mcq | fill_blank | short_answer | scenario
    level: Mapped[str] = mapped_column(String(20))  # recall | apply
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)  # chỉ cho mcq
    answer: Mapped[str] = mapped_column(Text)  # mcq: "A".."D"; còn lại: đáp án chuẩn
    explanation: Mapped[str] = mapped_column(Text, default="")
    rubric: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{"point": str, "weight": float}]
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # alt_answers, context_chunk_ids...
    source_quote: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="valid", index=True)  # valid | rejected
    reject_reason: Mapped[str] = mapped_column(String(300), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    chunk: Mapped[Chunk] = relationship(back_populates="questions")


class User(Base):
    """Người học. Chưa có đăng nhập thật: chỉ có tên hiển thị."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QuizSession(Base):
    """Một phiên học. `current_question_id` là câu đang chờ trả lời (để gọi /next lặp lại không đổi câu)."""

    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    num_questions: Mapped[int] = mapped_column(Integer, default=5)
    current_question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | finished
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    attempts: Mapped[list["Attempt"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Attempt(Base):
    """Một lần trả lời. `graded_by`: rule (luật), llm (chấm bằng AI) hoặc fallback (AI lỗi, chấm bằng từ khoá)."""

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    user_answer: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    feedback: Mapped[str] = mapped_column(Text, default="")
    missing_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    graded_by: Mapped[str] = mapped_column(String(20), default="rule")  # rule | llm | fallback
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    session: Mapped[QuizSession] = relationship(back_populates="attempts")


class Mastery(Base):
    """Mức thành thạo của một user với một chunk (đơn vị tri thức)."""

    __tablename__ = "mastery"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True)
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

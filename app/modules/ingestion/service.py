"""Quy trình nạp tài liệu: đọc -> chia chunk -> nhúng vector -> lưu CSDL và vector store."""

import hashlib
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Attempt, Chunk, Document, Mastery, Question, QuizSession
from app.modules.embedding.base import Embedder
from app.modules.ingestion.chunker import chunk_text
from app.modules.ingestion.loaders import load_text
from app.modules.vectorstore.numpy_store import NumpyVectorStore


@dataclass
class IngestResult:
    """Kết quả nạp; `already_existed` = True khi nội dung đã có từ trước (không tạo mới)."""

    document: Document
    num_chunks: int
    already_existed: bool


def chunk_embedding_text(heading: str, text: str) -> str:
    """Văn bản dùng để tạo vector: ghép tiêu đề vào nội dung để ngữ nghĩa mục được tính vào vector."""
    return f"{heading}\n{text}" if heading else text


class IngestionService:
    """Nạp/xoá tài liệu. Giữ CSDL (chunk) và vector store đồng bộ với nhau."""

    def __init__(self, settings: Settings, embedder: Embedder, store: NumpyVectorStore):
        self.s = settings
        self.embedder = embedder
        self.store = store

    def ingest_bytes(self, db: Session, filename: str, data: bytes, title: str | None = None) -> IngestResult:
        text = load_text(filename, data)
        return self.ingest_text(db, text, title or filename.rsplit(".", 1)[0], source=filename)

    def ingest_text(self, db: Session, text: str, title: str, source: str = "") -> IngestResult:
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = db.scalar(select(Document).where(Document.content_hash == content_hash))
        if existing:  # idempotent: ingest cùng nội dung hai lần không tạo trùng
            n = len(existing.chunks)
            return IngestResult(existing, n, True)

        raw = chunk_text(text, self.s.chunk_max_chars, self.s.chunk_overlap_chars, self.s.chunk_min_chars)
        if not raw:
            raise ValueError("Tài liệu không có nội dung để chia chunk.")

        doc = Document(title=title, source=source, content_hash=content_hash)
        # Thứ tự quan trọng: flush trước để chunk có id, vì vector store lưu theo id chunk.
        doc.chunks = [Chunk(position=i, heading=c.heading, text=c.text) for i, c in enumerate(raw)]
        db.add(doc)
        db.flush()  # có id cho chunk

        vecs = self.embedder.embed([chunk_embedding_text(c.heading, c.text) for c in doc.chunks])
        self.store.add([c.id for c in doc.chunks], vecs)
        db.commit()  # chỉ commit sau khi vector đã ghi xong, tránh DB có chunk mà thiếu vector
        return IngestResult(doc, len(doc.chunks), False)

    def delete_document(self, db: Session, document_id: int) -> bool:
        """Xoá tài liệu cùng chunk, câu hỏi, lượt trả lời, mastery và vector liên quan. False nếu không tồn tại."""
        doc = db.get(Document, document_id)
        if not doc:
            return False
        ids = [c.id for c in doc.chunks]
        qids = list(db.scalars(select(Question.id).where(Question.chunk_id.in_(ids)))) if ids else []
        # dọn dữ liệu tham chiếu (SQLite mặc định không tự cascade qua FK)
        if qids:
            db.execute(update(QuizSession).where(QuizSession.current_question_id.in_(qids)).values(current_question_id=None))
            db.execute(delete(Attempt).where(Attempt.question_id.in_(qids)))
        if ids:
            db.execute(delete(Mastery).where(Mastery.chunk_id.in_(ids)))
        db.execute(update(QuizSession).where(QuizSession.document_id == document_id).values(document_id=None))
        db.delete(doc)
        db.commit()
        self.store.delete(ids)
        return True

"""Chọn bộ nhúng theo cấu hình EMBEDDING_PROVIDER (gọi từ app/container.py)."""

from app.config import Settings
from app.modules.embedding.base import Embedder


def build_embedder(s: Settings) -> Embedder:
    """"hashing" -> bản offline; còn lại -> sentence-transformers với mô hình `s.embedding_model`.

    Import nằm trong nhánh để không bắt buộc cài sentence-transformers khi chỉ dùng bản băm.
    Đổi embedding model giữa chừng thì phải nạp lại tài liệu (số chiều vector đổi, vector store sẽ báo lỗi)."""
    if s.embedding_provider == "hashing":
        from app.modules.embedding.hashing import HashingEmbedder

        return HashingEmbedder()
    from app.modules.embedding.sentence_transformer import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder(s.embedding_model)

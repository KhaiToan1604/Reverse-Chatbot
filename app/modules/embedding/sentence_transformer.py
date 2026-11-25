"""Bộ nhúng thật chạy local bằng thư viện sentence-transformers. Chọn bằng EMBEDDING_PROVIDER=sentence_transformers."""

import numpy as np


class SentenceTransformerEmbedder:
    """Embedding thật, chạy local, miễn phí (vd. BAAI/bge-m3, intfloat/multilingual-e5-small).

    Cần `pip install sentence-transformers`. Mô hình tải lần đầu từ Hugging Face.
    Với họ e5, nên thêm tiền tố "query: " / "passage: " ở nơi gọi nếu muốn tối ưu.
    """

    def __init__(self, model_name: str):
        """Tải mô hình `model_name` (lần đầu cần mạng, vài trăm MB đến vài GB). Ném RuntimeError nếu chưa cài thư viện."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Cần cài: pip install sentence-transformers") from e
        self.name = model_name
        self._model = SentenceTransformer(model_name)
        # sentence-transformers >= 5 đổi tên hàm; giữ tên cũ làm dự phòng cho bản cài cũ.
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dim = int(get_dim())

    def embed(self, texts: list[str]) -> np.ndarray:
        """Ma trận (n, dim) float32 đã chuẩn hoá L2 (nên cosine = tích vô hướng); xử lý theo lô 16 đoạn cho đỡ tốn RAM."""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = self._model.encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
        return np.asarray(out, dtype=np.float32)

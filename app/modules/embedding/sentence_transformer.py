import numpy as np


class SentenceTransformerEmbedder:
    """Embedding thật, chạy local, miễn phí (vd. BAAI/bge-m3, intfloat/multilingual-e5-small).

    Cần `pip install sentence-transformers`. Mô hình tải lần đầu từ Hugging Face.
    Với họ e5, nên thêm tiền tố "query: " / "passage: " ở nơi gọi nếu muốn tối ưu.
    """

    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Cần cài: pip install sentence-transformers") from e
        self.name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = self._model.encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
        return np.asarray(out, dtype=np.float32)

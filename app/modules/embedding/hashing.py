"""Bộ nhúng offline bằng kỹ thuật băm (không cần tải mô hình). Chọn bằng EMBEDDING_PROVIDER=hashing."""

import re
import unicodedata
import zlib

import numpy as np


class HashingEmbedder:
    """Embedding offline không cần mô hình: băm từ + char-3gram vào vector cố định.

    Chỉ dùng để phát triển và demo offline. Chất lượng ngữ nghĩa kém xa mô hình thật
    (bge-m3, multilingual-e5) — khi chạy thật hãy dùng sentence_transformers.
    """

    name = "hashing"

    def __init__(self, dim: int = 512):
        """`dim` = số chiều vector; lớn hơn thì ít va chạm băm hơn nhưng tốn bộ nhớ hơn."""
        self.dim = dim

    @staticmethod
    def _tokens(text: str) -> list[str]:
        """Tách từ đơn giản sau khi chuẩn hoá NFC và hạ chữ thường."""
        text = unicodedata.normalize("NFC", text).lower()
        return re.findall(r"\w+", text)

    def _vec(self, text: str) -> np.ndarray:
        """Vector chuẩn hoá L2 của một đoạn: đặc trưng gồm từng từ và các lát cắt 3 ký tự (giúp bắt lỗi chính tả/biến thể từ)."""
        v = np.zeros(self.dim, dtype=np.float32)
        toks = self._tokens(text)
        feats = list(toks)
        joined = " ".join(toks)
        feats += [joined[i : i + 3] for i in range(max(0, len(joined) - 2))]
        # "Mẹo băm": mỗi đặc trưng cộng +1/-1 vào một ô (theo hash) -> vector cố định chiều, chuẩn hoá L2 ở cuối.
        for f in feats:
            h = zlib.crc32(f.encode("utf-8"))
            v[h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str]) -> np.ndarray:
        """Ma trận (n, dim) float32 đã chuẩn hoá L2; danh sách rỗng trả ma trận (0, dim)."""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self._vec(t) for t in texts])

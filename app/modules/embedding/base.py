"""Giao diện của bộ nhúng vector. Dùng Protocol nên bản giả/bản thật chỉ cần đúng chữ ký, không cần kế thừa."""

from typing import Protocol

import numpy as np


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Trả về ma trận (n, dim) float32, đã chuẩn hoá L2 (cosine = tích vô hướng)."""
        ...

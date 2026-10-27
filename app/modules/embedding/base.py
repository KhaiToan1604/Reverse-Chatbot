from typing import Protocol

import numpy as np


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Trả về ma trận (n, dim) float32, đã chuẩn hoá L2 (cosine = tích vô hướng)."""
        ...

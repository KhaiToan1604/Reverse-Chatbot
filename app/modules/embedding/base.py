"""Giao diện của bộ nhúng vector (biến văn bản thành vector để so độ giống nhau).

Dùng Protocol nên một bộ nhúng mới chỉ cần có `name`, `dim` và `embed(texts)`, không cần kế thừa.
Muốn thêm bộ nhúng: viết lớp mới trong thư mục này, rồi thêm nhánh chọn trong factory.py và giá trị mới cho
`embedding_provider` ở app/config.py."""

from typing import Protocol

import numpy as np


class Embedder(Protocol):
    """Hợp đồng chung: `name` hiện ở /health, `dim` là số chiều vector (phải cố định cho cả vector store)."""

    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Trả về ma trận (n, dim) float32, đã chuẩn hoá L2 (cosine = tích vô hướng)."""
        ...

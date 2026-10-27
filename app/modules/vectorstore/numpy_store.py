"""Vector store tối giản: ma trận numpy + cosine, lưu ra đĩa.

Với vài trăm đến vài chục nghìn chunk thì brute-force cosine là quá đủ và không cần phụ thuộc
thêm. Interface (add / delete / search) đủ nhỏ để thay bằng ChromaDB hoặc FAISS sau này.
"""

import json
import threading
from pathlib import Path

import numpy as np


class NumpyVectorStore:
    def __init__(self, path: str | None = None):
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        self._ids: list[int] = []
        self._mat: np.ndarray | None = None
        if self._path and (self._path / "ids.json").exists():
            self._ids = json.loads((self._path / "ids.json").read_text())
            self._mat = np.load(self._path / "vectors.npy")

    def _persist(self) -> None:
        if not self._path:
            return
        self._path.mkdir(parents=True, exist_ok=True)
        np.save(self._path / "vectors.npy", self._mat if self._mat is not None else np.zeros((0, 1), np.float32))
        (self._path / "ids.json").write_text(json.dumps(self._ids))

    def count(self) -> int:
        return len(self._ids)

    def add(self, ids: list[int], vectors: np.ndarray) -> None:
        """Upsert theo id."""
        if len(ids) != len(vectors):
            raise ValueError("ids và vectors lệch số lượng")
        if not ids:
            return
        with self._lock:
            self._delete_locked(ids)
            vectors = vectors.astype(np.float32)
            if self._mat is not None and len(self._ids) and self._mat.shape[1] != vectors.shape[1]:
                raise ValueError(
                    f"Số chiều embedding ({vectors.shape[1]}) khác vector store ({self._mat.shape[1]}). "
                    "Đã đổi embedding model? Hãy ingest lại từ đầu."
                )
            self._mat = vectors if not self._ids or self._mat is None else np.vstack([self._mat, vectors])
            self._ids.extend(ids)
            self._persist()

    def _delete_locked(self, ids: list[int]) -> None:
        if not self._ids or self._mat is None:
            return
        drop = set(ids)
        keep = [i for i, cid in enumerate(self._ids) if cid not in drop]
        if len(keep) == len(self._ids):
            return
        self._mat = self._mat[keep] if keep else None
        self._ids = [self._ids[i] for i in keep]

    def delete(self, ids: list[int]) -> None:
        with self._lock:
            self._delete_locked(ids)
            self._persist()

    def search(
        self, query: np.ndarray, k: int = 3, allowed_ids: set[int] | None = None, exclude_ids: set[int] | None = None
    ) -> list[tuple[int, float]]:
        with self._lock:
            if self._mat is None or not self._ids:
                return []
            scores = self._mat @ query.astype(np.float32).reshape(-1)
            order = np.argsort(-scores)
            out: list[tuple[int, float]] = []
            for idx in order:
                cid = self._ids[idx]
                if allowed_ids is not None and cid not in allowed_ids:
                    continue
                if exclude_ids and cid in exclude_ids:
                    continue
                out.append((cid, float(scores[idx])))
                if len(out) >= k:
                    break
            return out

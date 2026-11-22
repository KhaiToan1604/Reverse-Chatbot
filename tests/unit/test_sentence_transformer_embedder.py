"""SentenceTransformerEmbedder với mô hình giả: không tải mô hình thật, nhưng kiểm hợp đồng và tương thích tên hàm."""

import sys
import types

import numpy as np
import pytest

from app.config import Settings
from app.modules.embedding.factory import build_embedder
from app.modules.embedding.hashing import HashingEmbedder
from app.modules.embedding.sentence_transformer import SentenceTransformerEmbedder


def _install_fake(monkeypatch, dim_method):
    class FakeModel:
        def __init__(self, name):
            self.name = name
            setattr(self, dim_method, lambda: 4)

        def encode(self, texts, normalize_embeddings, batch_size, show_progress_bar):
            assert normalize_embeddings is True and show_progress_bar is False
            return [[float(len(t)), 1.0, 0.0, 0.0] for t in texts]

    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)


@pytest.mark.parametrize("dim_method", ["get_embedding_dimension", "get_sentence_embedding_dimension"])
def test_dimension_works_with_new_and_old_sentence_transformers(monkeypatch, dim_method):
    _install_fake(monkeypatch, dim_method)
    emb = SentenceTransformerEmbedder("fake/model")
    assert emb.dim == 4 and emb.name == "fake/model"


def test_embed_returns_float32_matrix_and_handles_empty_input(monkeypatch):
    _install_fake(monkeypatch, "get_embedding_dimension")
    emb = SentenceTransformerEmbedder("fake/model")
    out = emb.embed(["a", "bb"])
    assert out.dtype == np.float32 and out.shape == (2, 4)
    empty = emb.embed([])
    assert empty.shape == (0, 4) and empty.dtype == np.float32


def test_missing_package_gives_actionable_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # import sẽ ném ImportError
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        SentenceTransformerEmbedder("x")


def test_factory_chooses_provider(monkeypatch):
    _install_fake(monkeypatch, "get_embedding_dimension")
    base = {"database_url": "sqlite:///:memory:", "llm_provider": "mock", "_env_file": None}
    assert isinstance(build_embedder(Settings(embedding_provider="hashing", **base)), HashingEmbedder)
    real = build_embedder(Settings(embedding_provider="sentence_transformers", embedding_model="fake/m", **base))
    assert isinstance(real, SentenceTransformerEmbedder) and real.name == "fake/m"

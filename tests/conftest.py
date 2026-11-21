from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.base import dispose_engine
from app.main import create_app

SAMPLE = Path(__file__).parent.parent / "data" / "sample"


@pytest.fixture
def settings():
    return Settings(database_url="sqlite:///:memory:", vector_store_path=":memory:", llm_provider="mock",
                    embedding_provider="hashing", _env_file=None)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
    dispose_engine()


@pytest.fixture
def loaded(client):
    """Client đã nạp tài liệu mẫu."""
    ids = []
    for f in sorted(SAMPLE.glob("*.md")):
        r = client.post("/documents", files={"file": (f.name, f.read_bytes(), "text/markdown")})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return client, ids


def pytest_collection_modifyitems(items):
    """Tự gắn marker theo thư mục: unit / integration / e2e."""
    for item in items:
        for layer in ("unit", "integration", "e2e"):
            if f"/tests/{layer}/" in str(item.fspath).replace("\\", "/"):
                item.add_marker(getattr(pytest.mark, layer))

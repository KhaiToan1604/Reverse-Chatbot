import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "sample"
ADMIN_KEY = "e2e-admin-key"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Chạy uvicorn thật (mock LLM, hashing embedding, DB tạm) và nạp tài liệu mẫu."""
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        pytest.skip("Chưa build frontend (cd frontend && npm run build)")
    tmp = tmp_path_factory.mktemp("e2e")
    port = _free_port()
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tmp / 'e2e.db'}",
        "VECTOR_STORE_PATH": str(tmp / "vec"),
        "LLM_PROVIDER": "mock",
        "EMBEDDING_PROVIDER": "hashing",
        "ADMIN_API_KEY": ADMIN_KEY,
        "FRONTEND_DIST": str(ROOT / "frontend" / "dist"),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Server không khởi động được")
        h = {"X-Admin-Key": ADMIN_KEY}
        for f in sorted(SAMPLE.glob("*.md")):
            r = httpx.post(f"{base}/documents", headers=h, files={"file": (f.name, f.read_bytes(), "text/markdown")}, timeout=60)
            assert r.status_code == 201, r.text
            g = httpx.post(f"{base}/questions/generate", headers=h, json={"document_id": r.json()["id"]}, timeout=120)
            assert g.status_code == 200 and g.json()["created"] > 0, g.text
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)

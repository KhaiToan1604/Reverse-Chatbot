import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import SAMPLE

ROOT = Path(__file__).resolve().parents[2]


def _cli_env(tmp_path: Path) -> dict:
    """Môi trường cho tiến trình con: kế thừa môi trường hiện tại (Windows cần SYSTEMROOT để khởi tạo socket/asyncio)
    rồi ghi đè để dùng DB tạm, LLM giả, embedding băm (biến môi trường luôn thắng file .env)."""
    return {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'c.db'}",
        "VECTOR_STORE_PATH": str(tmp_path / "v"),
        "LLM_PROVIDER": "mock",
        "EMBEDDING_PROVIDER": "hashing",
        "ADMIN_API_KEY": "",
    }


def test_unsupported_upload_415_and_unknown_session_404(client):
    r = client.post("/documents", files={"file": ("a.exe", b"x", "application/octet-stream")})
    assert r.status_code == 415
    assert client.get("/quiz/sessions/99999/next").status_code == 404


def test_quiz_requires_content(client):
    u = client.post("/users", json={"display_name": "T"}).json()
    s = client.post("/quiz/sessions", json={"user_id": u["id"], "num_questions": 1})
    assert s.status_code == 201
    assert client.get(f"/quiz/sessions/{s.json()['session_id']}/next").status_code == 409


def test_evaluate_cli_report_on_fresh_db(tmp_path):
    env = _cli_env(tmp_path)
    out = subprocess.run([sys.executable, "-m", "scripts.evaluate", "report"], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=60, check=False)
    assert out.returncode == 0, out.stderr
    assert "generated_total" in out.stdout


def test_ingest_cli_loads_samples(tmp_path):
    env = _cli_env(tmp_path)
    out = subprocess.run([sys.executable, "-m", "scripts.ingest", str(SAMPLE)], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=60, check=False)
    assert out.returncode == 0, out.stderr

"""E2E mức HTTP: server uvicorn thật, đi trọn luồng học viên."""

import httpx

from tests.e2e.conftest import ADMIN_KEY


def test_admin_protected_and_public_catalog(live_server):
    assert httpx.get(f"{live_server}/questions").status_code in (401, 403)
    assert httpx.get(f"{live_server}/questions", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 200
    assert len(httpx.get(f"{live_server}/catalog").json()) >= 1


def test_full_learner_journey_over_http(live_server):
    u = httpx.post(f"{live_server}/users", json={"display_name": "E2E"}).json()
    s = httpx.post(f"{live_server}/quiz/sessions", json={"user_id": u["id"], "num_questions": 2}).json()
    sid = s["session_id"]
    for _ in range(2):
        q = httpx.get(f"{live_server}/quiz/sessions/{sid}/next").json()
        assert q["question"]["question_id"]
        ans = "A" if q["question"]["qtype"] == "mcq" else "thẻ sinh viên"
        r = httpx.post(f"{live_server}/quiz/sessions/{sid}/answer", json={"question_id": q["question"]["question_id"], "answer": ans})
        assert r.status_code == 200
        assert 0 <= r.json()["score"] <= 1
    summ = httpx.get(f"{live_server}/quiz/sessions/{sid}/summary").json()
    assert summ["answered"] == 2
    assert httpx.get(f"{live_server}/users/{u['id']}/progress").status_code == 200

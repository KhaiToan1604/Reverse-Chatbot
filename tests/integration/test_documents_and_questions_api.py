"""Router quản trị tài liệu và câu hỏi: các nhánh lỗi, bộ lọc và vòng đời (tạo, xem, xoá)."""

import pytest

from app.api.routers import documents

TEXT = "# Nội quy\n\nSinh viên được mượn tối đa 5 cuốn sách trong 14 ngày. Sách trả trễ bị phạt 2.000 đồng mỗi cuốn mỗi ngày."


def test_ingest_text_then_duplicate_is_flagged(client):
    r1 = client.post("/documents/text", json={"title": "Nội quy", "text": TEXT})
    assert r1.status_code == 201 and r1.json()["already_existed"] is False and r1.json()["num_chunks"] >= 1
    r2 = client.post("/documents/text", json={"title": "Nội quy bản sao", "text": TEXT})
    assert r2.json()["already_existed"] is True and r2.json()["id"] == r1.json()["id"]


@pytest.mark.parametrize("body", [{"title": "x", "text": "quá ngắn"}, {"title": "", "text": TEXT}, {"text": TEXT}])
def test_ingest_text_validation_returns_422(client, body):
    assert client.post("/documents/text", json=body).status_code == 422


def test_upload_too_large_returns_413(client, monkeypatch):
    monkeypatch.setattr(documents, "MAX_UPLOAD", 10)
    r = client.post("/documents", files={"file": ("a.md", TEXT.encode(), "text/markdown")})
    assert r.status_code == 413


def test_upload_empty_file_returns_422(client):
    r = client.post("/documents", files={"file": ("rong.md", b"   \n", "text/markdown")})
    assert r.status_code == 422


def test_list_documents_and_chunks(loaded):
    client, ids = loaded
    docs = client.get("/documents").json()
    assert [d["id"] for d in docs] == sorted(ids) and all(d["num_chunks"] > 0 for d in docs)
    chunks = client.get(f"/documents/{ids[0]}/chunks").json()
    assert [c["position"] for c in chunks] == sorted(c["position"] for c in chunks)
    assert all(c["text"] for c in chunks)


def test_chunks_of_unknown_document_is_404(client):
    assert client.get("/documents/999/chunks").status_code == 404


def test_delete_document_removes_its_chunks_and_questions(loaded):
    client, ids = loaded
    client.post("/questions/generate", json={"document_id": ids[0]})
    assert client.get("/questions", params={"document_id": ids[0]}).json()
    assert client.delete(f"/documents/{ids[0]}").status_code == 204
    assert client.get(f"/documents/{ids[0]}/chunks").status_code == 404
    assert client.get("/questions", params={"document_id": ids[0]}).json() == []
    assert client.delete(f"/documents/{ids[0]}").status_code == 404


def test_generate_for_single_chunk_with_custom_specs(loaded):
    client, ids = loaded
    chunk_id = client.get(f"/documents/{ids[0]}/chunks").json()[0]["id"]
    r = client.post("/questions/generate", json={"chunk_id": chunk_id, "specs": [{"qtype": "mcq", "level": "recall", "count": 1}]})
    body = r.json()
    assert r.status_code == 200 and {q["qtype"] for q in body["questions"]} <= {"mcq"}
    assert body["created"] == len(body["questions"]) and body["rejected"] == len(body["rejected_reasons"])


@pytest.mark.parametrize(("body", "code"), [
    ({}, 422),                                                                    # thiếu document_id/chunk_id
    ({"chunk_id": 999}, 404),                                                     # chunk không tồn tại
    ({"document_id": 1, "specs": [{"qtype": "essay", "level": "recall"}]}, 422),  # loại câu lạ
    ({"document_id": 1, "specs": [{"qtype": "mcq", "level": "expert"}]}, 422),    # mức lạ
    ({"document_id": 1, "specs": [{"qtype": "mcq", "level": "recall", "count": 9}]}, 422),  # quá giới hạn count
])
def test_generate_rejects_bad_requests(loaded, body, code):
    client, _ = loaded
    assert client.post("/questions/generate", json=body).status_code == code


def test_list_questions_filters(loaded):
    client, ids = loaded
    client.post("/questions/generate", json={"document_id": ids[0]})
    everything = client.get("/questions", params={"document_id": ids[0]}).json()
    assert everything and all(q["status"] == "valid" for q in everything)

    only_mcq = client.get("/questions", params={"document_id": ids[0], "qtype": "mcq"}).json()
    assert only_mcq and all(q["qtype"] == "mcq" for q in only_mcq)
    only_apply = client.get("/questions", params={"document_id": ids[0], "level": "apply"}).json()
    assert only_apply and all(q["level"] == "apply" for q in only_apply)
    assert len(client.get("/questions", params={"document_id": ids[0], "limit": 1}).json()) == 1
    assert client.get("/questions", params={"document_id": ids[0], "offset": 10_000}).json() == []
    assert client.get("/questions", params={"document_id": ids[1]}).json() == []  # chưa sinh cho tài liệu 2
    assert client.get("/questions", params={"limit": 501}).status_code == 422


def test_get_question_detail_and_unknown(loaded):
    client, ids = loaded
    client.post("/questions/generate", json={"document_id": ids[0]})
    first = client.get("/questions", params={"document_id": ids[0]}).json()[0]
    detail = client.get(f"/questions/{first['id']}").json()
    assert detail["id"] == first["id"] and detail["source_quote"] and detail["answer"]
    assert client.get("/questions/999999").status_code == 404

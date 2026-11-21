def test_catalog_is_public_and_hides_content(loaded):
    client, ids = loaded
    r = client.get("/catalog")
    assert r.status_code == 200
    rows = r.json()
    assert [x["id"] for x in rows] == ids
    assert all(set(x) == {"id", "title", "num_topics", "has_questions"} for x in rows)
    assert not any(x["has_questions"] for x in rows)
    client.post("/questions/generate", json={"document_id": ids[0]})
    assert client.get("/catalog").json()[0]["has_questions"] is True

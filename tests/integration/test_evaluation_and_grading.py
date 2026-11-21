import csv

import pytest

from app.db.base import session_scope
from app.modules.evaluation import runner
from app.modules.llm.base import LLMError, LLMProvider


def _generate_all(client, ids):
    for i in ids:
        r = client.post("/questions/generate", json={"document_id": i})
        assert r.status_code == 200


def test_quality_report_and_review_roundtrip(loaded, tmp_path):
    client, ids = loaded
    _generate_all(client, ids)
    with session_scope() as db:
        rep = runner.question_quality_report(db)
        assert rep["generated_total"] > 0
        assert rep["valid"] + rep["rejected"] == rep["generated_total"]
        path = tmp_path / "rev.csv"
        n = runner.export_review_csv(db, str(path), n=5)
    assert 0 < n <= 5
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["human_ok(1/0)"] = "1"
    rows[0]["human_ok(1/0)"] = "0"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    out = runner.import_review_labels(str(path))
    assert out["labeled"] == len(rows)
    assert out["human_pass_rate"] == pytest.approx((len(rows) - 1) / len(rows), abs=1e-4)


def test_import_review_without_labels(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("question_id,qtype,level,human_ok(1/0)\n1,mcq,recall,\n", encoding="utf-8")
    assert runner.import_review_labels(str(p)) == {"labeled": 0}


def test_cohen_kappa_known_values():
    assert runner.cohen_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert runner.cohen_kappa([True, True, False, False], [True, False, True, False]) == 0.0
    assert runner.cohen_kappa([], []) != runner.cohen_kappa([], [])  # NaN


def test_grader_agreement_and_rag_vs_norag(loaded, tmp_path):
    client, ids = loaded
    _generate_all(client, ids)
    c = client.app.state.container
    with session_scope() as db:
        qs = client.get("/questions", params={"limit": 3}, headers={}).json()
        path = tmp_path / "g.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["question_id", "answer", "human_score"])
            for q in qs:
                w.writerow([q["id"], q["answer"], 1.0])
            w.writerow([999999, "x", 0.0])  # id không tồn tại -> bỏ qua
        res = runner.grader_agreement(db, c.grader, str(path), 0.6)
        assert res["n"] == len(qs)
        assert res["pass_fail_accuracy"] == 1.0 and res["mae"] == 0.0
        cmp = runner.rag_vs_norag(db, c.generation, n_chunks=2)
        assert set(cmp) == {"rag", "no_rag"}
        assert cmp["rag"]["generated"] > 0


class _BrokenLLM(LLMProvider):
    name = "broken"

    def complete(self, system, user, *, json_mode=True, temperature=0.3):
        raise LLMError("down")


def test_essay_grader_falls_back_to_heuristic_when_llm_down(loaded):
    client, ids = loaded
    _generate_all(client, ids)
    c = client.app.state.container
    from app.db.models import Question
    from app.modules.grading.llm_grader import LLMGrader

    with session_scope() as db:
        q = db.query(Question).filter(Question.qtype.in_(["short_answer", "scenario"]), Question.status == "valid").first()
        assert q is not None
        g = LLMGrader(_BrokenLLM(), 0.6)
        r = g.grade(q, q.answer)
        assert r.graded_by == "fallback" and r.score > 0
        r2 = c.grader.grade(q, q.answer)
        assert r2.graded_by in ("llm", "fallback")


def test_fill_blank_wrong_answer_is_marked_incorrect(loaded):
    client, ids = loaded
    _generate_all(client, ids)
    c = client.app.state.container
    from app.db.models import Question

    with session_scope() as db:
        q = db.query(Question).filter(Question.qtype == "fill_blank", Question.status == "valid").first()
        assert q is not None
        assert c.grader.grade(q, q.answer).is_correct
        assert not c.grader.grade(q, "zzzz qqqq").is_correct


def test_duplicates_excluded_from_pass_rate_and_purgeable(loaded):
    client, ids = loaded
    _generate_all(client, ids)
    _generate_all(client, ids)  # chạy lặp: các câu giống nhau bị loại vì trùng
    with session_scope() as db:
        rep = runner.question_quality_report(db)
        assert rep["duplicate_rejected"] > 0
        assert rep["evaluated"] == rep["generated_total"] - rep["duplicate_rejected"]
        assert rep["auto_pass_rate"] == pytest.approx(rep["valid"] / rep["evaluated"], abs=1e-4)
        n = runner.purge_duplicate_rejects(db)
        assert n == rep["duplicate_rejected"]
        after = runner.question_quality_report(db)
        assert after["duplicate_rejected"] == 0 and after["valid"] == rep["valid"]

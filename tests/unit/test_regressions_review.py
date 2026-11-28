"""Hồi quy cho các lỗi tìm thấy khi rà soát mã (trọng số rubric, chấm MCQ, hạn mức LLM, vector store)."""

import httpx
import numpy as np
import pytest

from app.db.models import Question
from app.modules.generation.rules import finalize
from app.modules.generation.schemas import RawQuestion
from app.modules.grading.rule_based import grade_mcq
from app.modules.llm.base import LLMError, LLMRateLimited
from app.modules.llm.http_providers import _post_with_retry
from app.modules.vectorstore.numpy_store import NumpyVectorStore


def _scenario(weights):
    return RawQuestion.model_validate({
        "qtype": "scenario", "level": "apply", "question": "Tình huống: bạn làm gì tiếp theo?", "answer": "x",
        "source_quote": "một hai ba bốn", "explanation": "e",
        "rubric": [{"point": f"p{i}", "weight": w} for i, w in enumerate(weights)],
    })


@pytest.mark.parametrize("weights", [[0, 1], [0, 0], [-1, 2, 0], [0.5, 0.5], [3, 1]])
def test_rubric_weights_sum_to_one_and_stay_positive(weights):
    ws = [r["weight"] for r in finalize(_scenario(weights))["rubric"]]
    assert sum(ws) == pytest.approx(1.0, abs=1e-6)
    assert all(w > 0 for w in ws)


def test_mcq_typed_option_text_beats_letter_guess():
    q = Question(qtype="mcq", answer="B", options=["xin chào", "a b c", "ba", "bốn"])
    assert grade_mcq(q, "a b c").is_correct  # nội dung lựa chọn B, không phải chữ cái A
    assert not grade_mcq(q, "A").is_correct
    assert grade_mcq(q, "b)").is_correct
    assert not grade_mcq(q, "...").is_correct  # chỉ dấu câu


class _Client:
    def __init__(self, results):
        self.results = list(results)

    def post(self, url, **kw):
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _resp(code):
    return httpx.Response(code, request=httpx.Request("POST", "http://x"))


def test_network_error_after_429_is_plain_llm_error(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    c = _Client([_resp(429), httpx.ConnectError("boom")])
    with pytest.raises(LLMError) as ei:
        _post_with_retry(c, "http://x", retries=1)
    assert not isinstance(ei.value, LLMRateLimited)


def test_still_429_after_retries_is_rate_limited(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    with pytest.raises(LLMRateLimited):
        _post_with_retry(_Client([_resp(429), _resp(429)]), "http://x", retries=1)


def test_vector_dim_mismatch_keeps_old_vectors():
    st = NumpyVectorStore()
    st.add([1, 2], np.eye(2, 3, dtype=np.float32))
    with pytest.raises(ValueError):
        st.add([1], np.ones((1, 5), dtype=np.float32))
    assert st.count() == 2

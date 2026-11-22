import json

import pytest

from app.modules.generation.validator import llm_validate_batch
from app.modules.llm.base import LLMProvider, LLMRateLimited

Q = {"qtype": "mcq", "question": "Câu hỏi?", "options": ["a", "b", "c", "d"], "answer": "A", "rubric": None}


class _Scripted(LLMProvider):
    name = "scripted"

    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, 0

    def complete(self, system, user, *, json_mode=True, temperature=0.3):
        self.calls += 1
        if self.exc:
            raise self.exc
        return json.dumps(self.reply)


def _ok(i, **kw):
    return {"index": i, "answerable": True, "answer_correct": True, "unambiguous": True, **kw}


def test_one_llm_call_for_whole_batch():
    llm = _Scripted({"results": [_ok(0), _ok(1), _ok(2)]})
    out = llm_validate_batch(llm, "ctx", [Q, Q, Q])
    assert llm.calls == 1
    assert [ok for ok, _ in out] == [True, True, True]


def test_failed_and_missing_items_are_rejected():
    llm = _Scripted({"results": [_ok(0, answer_correct=False, reason="sai đáp án")]})  # thiếu index 1
    out = llm_validate_batch(llm, "ctx", [Q, Q])
    assert out[0][0] is False and "sai đáp án" in out[0][1]
    assert out[1][0] is False and "không trả kết quả" in out[1][1]


def test_wrong_format_rejects_all_with_snippet():
    llm = _Scripted("không phải danh sách")
    out = llm_validate_batch(llm, "ctx", [Q, Q])
    assert [ok for ok, _ in out] == [False, False]
    assert "sai định dạng" in out[0][1] and "không phải danh sách" in out[0][1]
    assert llm.calls == 3  # 1 lần cho lô + 1 lần mỗi câu (dự phòng)


class _Seq(LLMProvider):
    name = "seq"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def complete(self, system, user, *, json_mode=True, temperature=0.3):
        self.calls += 1
        return json.dumps(self.replies.pop(0))


def test_bad_batch_falls_back_to_per_question():
    llm = _Seq(["rác", _ok(0), _ok(0, answer_correct=False, reason="sai")])
    out = llm_validate_batch(llm, "ctx", [Q, Q])
    assert [ok for ok, _ in out] == [True, False]
    assert "sai" in out[1][1]


def test_single_dict_result_accepted_for_one_question():
    assert llm_validate_batch(_Scripted(_ok(0)), "ctx", [Q])[0][0] is True


def test_bare_list_and_positional_and_dict_keyed():
    ok = {"answerable": True, "answer_correct": True, "unambiguous": True}
    assert [o for o, _ in llm_validate_batch(_Scripted([_ok(0), _ok(1)]), "c", [Q, Q])] == [True, True]
    assert [o for o, _ in llm_validate_batch(_Scripted({"results": [ok, ok]}), "c", [Q, Q])] == [True, True]
    assert [o for o, _ in llm_validate_batch(_Scripted({"0": ok, "1": ok}), "c", [Q, Q])] == [True, True]
    assert [o for o, _ in llm_validate_batch(_Scripted({"results": {"0": ok}}), "c", [Q])] == [True]


def test_string_true_and_string_index():
    r = {"index": "0", "answerable": "true", "answer_correct": True, "unambiguous": True}
    assert llm_validate_batch(_Scripted({"results": [r]}), "c", [Q])[0][0] is True


def test_empty_batch_makes_no_call():
    llm = _Scripted({"results": []})
    assert llm_validate_batch(llm, "ctx", []) == []
    assert llm.calls == 0


def test_rate_limit_propagates_not_rejected():
    with pytest.raises(LLMRateLimited):
        llm_validate_batch(_Scripted(exc=LLMRateLimited("429")), "ctx", [Q])

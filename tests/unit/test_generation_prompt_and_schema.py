import pytest

from app.modules.generation.rules import unverified_numbers
from app.modules.generation.schemas import RawQuestion

CTX = "Sách trả trễ bị phạt 2.000 đồng cho mỗi cuốn mỗi ngày quá hạn."


def test_numbers_present_in_context_or_question_are_verified():
    assert unverified_numbers("2.000 đồng", CTX, "Phạt bao nhiêu?") == set()


def test_computed_number_is_flagged():
    assert unverified_numbers("30.000 đồng", CTX, "Mượn 3 cuốn trễ 5 ngày?")


def _raw(**kw):
    base = {"qtype": "mcq", "level": "recall", "question": "Q?", "source_quote": "x", "explanation": "e",
            "answer": "B", "options": ["a", "b", "c", "d"], "correct_index": 1}
    return RawQuestion(**{**base, **kw})


def test_options_dict_is_coerced_to_list():
    q = _raw(options={"A": "a", "B": "b", "C": "c", "D": "d"})
    assert q.options == ["a", "b", "c", "d"]


@pytest.mark.parametrize(("raw", "expected"), [("B", 1), ("B)", 1), ("2", 2), (3, 3)])
def test_correct_index_is_coerced(raw, expected):
    assert _raw(correct_index=raw).correct_index == expected

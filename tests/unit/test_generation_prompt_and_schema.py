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


def test_scenario_example_shows_a_multi_point_rubric_and_matches_its_quote():
    """Mẫu scenario phải minh hoạ rubric >= 2 ý và có đáp án nằm trong trích dẫn của chính mẫu (model hay sao chép mẫu)."""
    from app.modules.generation.prompts import _example

    ex = _example("scenario", "apply")
    assert len(ex["rubric"]) >= 2 and abs(sum(r["weight"] for r in ex["rubric"]) - 1) < 1e-9
    assert ex["source_quote"] and "15 phút" in ex["source_quote"] and "15 phút" in ex["explanation"]
    assert ex["options"] is None and ex["correct_index"] is None


def test_format_section_mentions_rubric_rule_only_for_open_questions():
    from app.modules.generation.prompts import _format_section
    from app.modules.generation.schemas import Spec

    assert "KHÔNG được null" in _format_section([Spec("scenario", "apply")])
    assert "KHÔNG được null" in _format_section([Spec("short_answer", "apply")])
    assert "LƯU Ý tự luận" not in _format_section([Spec("mcq", "recall")])


def test_prompt_asks_for_calculation_expression_before_the_answer():
    from app.modules.generation.prompts import SYSTEM_GENERATE, _example

    assert '"calculation"' in SYSTEM_GENERATE and "MỌI con số nêu trong câu hỏi" in SYSTEM_GENERATE
    keys = list(_example("mcq", "recall"))
    assert keys.index("explanation") < keys.index("calculation") < keys.index("answer")  # tính trước khi chốt đáp án

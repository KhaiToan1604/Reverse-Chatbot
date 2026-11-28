"""Các cải tiến giảm lỗi hình thức khi sinh câu hỏi: tự sửa chỗ trống, lý do validator có cờ, gom lý do loại, lưu ý trong prompt."""

import json

import pytest

from app.modules.evaluation.runner import reason_group
from app.modules.generation.prompts import build_generate_prompt
from app.modules.generation.rules import check_question, repair_fill_blank
from app.modules.generation.schemas import RawQuestion, Spec
from app.modules.generation.validator import llm_validate_batch
from app.modules.llm.base import LLMProvider

CTX = "Thư viện mở cửa lúc 8 giờ sáng và đóng cửa lúc 18 giờ. Máy scan đặt ở khu vực báo tạp chí tầng một."
QUOTE = "Thư viện mở cửa lúc 8 giờ sáng và đóng cửa lúc 18 giờ."


def _fill(**kw) -> RawQuestion:
    base = {"qtype": "fill_blank", "level": "recall", "question": "Thư viện mở cửa lúc 8 giờ sáng.", "answer": "8",
            "explanation": "e", "source_quote": QUOTE}
    return RawQuestion(**{**base, **kw})


def test_repair_replaces_answer_that_appears_once_and_then_passes_rules():
    q = _fill()
    assert check_question(q, CTX) == "fill_blank cần đúng một chỗ trống ____"  # trước khi sửa: bị loại như cũ
    repair_fill_blank(q)
    assert q.question == "Thư viện mở cửa lúc ____ giờ sáng."
    assert check_question(q, CTX) is None


def test_repair_matches_whole_token_only():
    # "8" nằm trong "18" nhưng không được thay; chỉ "8" đứng riêng mới được thay.
    q = _fill(question="Thư viện đóng cửa lúc 18 giờ, mở cửa lúc 8 giờ.")
    repair_fill_blank(q)
    assert q.question == "Thư viện đóng cửa lúc 18 giờ, mở cửa lúc ____ giờ."


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Thư viện mở cửa lúc ____ giờ sáng.", "8"),                    # đã có chỗ trống: không đụng
        ("Thư viện mở cửa lúc 8 giờ và đóng cửa lúc 8 giờ.", "8"),      # đáp án xuất hiện hai lần: mơ hồ, không sửa
        ("Máy scan đặt ở khu vực nào?", "báo tạp chí"),                   # đáp án không có trong câu hỏi: không sửa
        ("Thư viện mở cửa lúc 8 giờ sáng.", "   "),                       # đáp án rỗng: không sửa
    ],
)
def test_repair_leaves_question_unchanged_when_not_safe(question, answer):
    q = _fill(question=question, answer=answer)
    repair_fill_blank(q)
    assert q.question == question


def test_repair_ignores_other_question_types():
    q = RawQuestion(qtype="short_answer", level="apply", question="Thư viện mở cửa lúc 8 giờ sáng?", answer="8", explanation="e",
                    source_quote=QUOTE, rubric=[{"point": "8 giờ", "weight": 1.0}])
    repair_fill_blank(q)
    assert q.question == "Thư viện mở cửa lúc 8 giờ sáng?"


class _Scripted(LLMProvider):
    name = "scripted"

    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user, *, json_mode=True, temperature=0.3):
        return json.dumps(self.reply)


def test_validator_reason_lists_failed_flags_after_colon():
    reply = {"results": [{"index": 0, "answerable": True, "answer_correct": True, "unambiguous": False,
                          "reason": "CONTEXT chỉ rõ máy scan ở khu vực báo tạp chí."}]}
    ok, reason = llm_validate_batch(_Scripted(reply), "ctx", [{"qtype": "mcq", "question": "?", "answer": "A"}])[0]
    assert ok is False
    # Phần trước ":" giữ nguyên để báo cáo gom đúng nhóm; cờ nằm sau ":" để thấy tiêu chí nào false.
    assert reason.split(":")[0] == "validator loại"
    assert "unambiguous=False" in reason and "answerable=True" in reason and "báo tạp chí" in reason


@pytest.mark.parametrize(
    ("reason", "group"),
    [
        ("số trong đáp án (3000) không nằm trong source_quote: trích dẫn không đủ", "số trong đáp án không nằm trong source_quote"),
        ("số trong đáp án (000, 900) không nằm trong source_quote: x", "số trong đáp án không nằm trong source_quote"),
        ("đáp án chứa số không có trong tài liệu (70000): có thể là kết quả tính", "đáp án chứa số không có trong tài liệu"),
        ("validator loại: [answerable=True] lý do", "validator loại"),
        ("tự luận cần rubric ít nhất 2 ý", "tự luận cần rubric ít nhất 2 ý"),
        (None, ""),
    ],
)
def test_reason_group_drops_specific_numbers(reason, group):
    assert reason_group(reason) == group


def test_fill_blank_prompt_asks_for_a_statement_with_one_blank():
    system, _ = build_generate_prompt("Giờ mở cửa", CTX, [Spec("fill_blank", "recall")])
    assert "CÂU KHẲNG ĐỊNH" in system and "ĐÚNG MỘT chỗ trống" in system
    mcq_only, _ = build_generate_prompt("Giờ mở cửa", CTX, [Spec("mcq", "recall")])
    assert "LƯU Ý fill_blank" not in mcq_only  # chỉ thêm lưu ý khi có yêu cầu loại này

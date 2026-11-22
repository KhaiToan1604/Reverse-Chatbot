"""Luật kiểm tra câu hỏi (rules.py): mỗi nhánh loại câu phải trả đúng lý do, và câu đạt phải trả None."""

import pytest

from app.modules.generation.rules import check_question, ensure_rubric, finalize, grounded
from app.modules.generation.schemas import RawQuestion

CTX = (
    "Sách trả trễ bị phạt 2.000 đồng cho mỗi cuốn mỗi ngày quá hạn. "
    "Sinh viên được mượn tối đa 5 cuốn sách trong 14 ngày. Thư viện mở cửa từ 7 giờ đến 20 giờ các ngày trong tuần."
)
QUOTE = "Sinh viên được mượn tối đa 5 cuốn sách trong 14 ngày."


def _mcq(**kw):
    base = {"qtype": "mcq", "level": "recall", "question": "Sinh viên được mượn tối đa bao nhiêu cuốn?",
            "options": ["3 cuốn", "5 cuốn", "7 cuốn", "10 cuốn"], "correct_index": 1, "answer": "5 cuốn",
            "explanation": "theo quy định", "source_quote": QUOTE}
    return RawQuestion(**{**base, **kw})


def _fill(**kw):
    base = {"qtype": "fill_blank", "level": "recall", "question": "Sinh viên được mượn tối đa 5 cuốn sách trong ____ ngày.",
            "answer": "14", "explanation": "e", "source_quote": QUOTE}
    return RawQuestion(**{**base, **kw})


def _open(qtype="short_answer", **kw):
    base = {"qtype": qtype, "level": "apply", "question": "Sinh viên mượn sách được bao lâu và tối đa mấy cuốn?",
            "answer": "Được mượn tối đa 5 cuốn trong 14 ngày.", "explanation": "e", "source_quote": QUOTE,
            "rubric": [{"point": "tối đa 5 cuốn", "weight": 0.5}, {"point": "14 ngày", "weight": 0.5}]}
    return RawQuestion(**{**base, **kw})


def test_valid_questions_of_every_type_pass():
    assert check_question(_mcq(), CTX) is None
    assert check_question(_fill(), CTX) is None
    assert check_question(_open(), CTX) is None
    assert check_question(_open("scenario"), CTX) is None


@pytest.mark.parametrize(("kw", "msg"), [
    ({"qtype": "essay"}, "qtype"),
    ({"level": "expert"}, "level"),
    ({"question": "Ngắn?"}, "độ dài"),
    ({"question": "x" * 1300}, "độ dài"),
    ({"source_quote": "Câu này hoàn toàn không có trong tài liệu nào cả"}, "source_quote"),
])
def test_common_rejections(kw, msg):
    assert msg in (check_question(_mcq(**kw), CTX) or "")


@pytest.mark.parametrize(("kw", "msg"), [
    ({"options": ["a", "b", "c"]}, "4 lựa chọn"),
    ({"options": ["3 cuốn", "5 cuốn", "7 cuốn", ""]}, "4 lựa chọn"),
    ({"options": None}, "4 lựa chọn"),
    ({"options": ["5 cuốn", "5 cuốn", "7 cuốn", "10 cuốn"]}, "trùng"),
    ({"options": ["A. 3 cuốn", "B. 3 cuốn", "7 cuốn", "10 cuốn"]}, "trùng"),  # tiền tố A./B. bị bỏ trước khi so
    ({"correct_index": None}, "correct_index"),
    ({"correct_index": 4}, "correct_index"),
])
def test_mcq_rejections(kw, msg):
    assert msg in (check_question(_mcq(**kw), CTX) or "")


@pytest.mark.parametrize(("kw", "msg"), [
    ({"question": "Không có chỗ trống nào cả trong câu này."}, "một chỗ trống"),
    ({"question": "Mượn ____ cuốn trong ____ ngày theo quy định."}, "một chỗ trống"),
    ({"answer": ""}, "rỗng hoặc quá dài"),
    ({"answer": "một hai ba bốn năm sáu bảy"}, "rỗng hoặc quá dài"),
    ({"answer": "99"}, "không xuất hiện"),
])
def test_fill_blank_rejections(kw, msg):
    assert msg in (check_question(_fill(**kw), CTX) or "")


@pytest.mark.parametrize("blank", ["____", "......", "………"])
def test_fill_blank_accepts_common_blank_styles(blank):
    q = _fill(question=f"Sinh viên được mượn tối đa 5 cuốn sách trong {blank} ngày.")
    assert check_question(q, CTX) is None


@pytest.mark.parametrize(("kw", "msg"), [
    ({"answer": " "}, "thiếu đáp án"),
    ({"rubric": None}, "rubric"),
    ({"rubric": [{"point": "ý một"}, {"point": "  "}]}, "rỗng"),
])
def test_open_question_rejections(kw, msg):
    assert msg in (check_question(_open(**kw), CTX) or "")


def test_short_answer_may_have_a_single_rubric_point_but_scenario_may_not():
    one = [{"point": "tối đa 5 cuốn", "weight": 1.0}]
    assert check_question(_open("short_answer", rubric=one), CTX) is None
    assert "ít nhất 2 ý" in (check_question(_open("scenario", rubric=one), CTX) or "")


def test_ensure_rubric_fills_missing_rubric_of_short_answer_from_answer():
    q = _open("short_answer", rubric=None)
    ensure_rubric(q)
    assert [(r.point, r.weight) for r in q.rubric] == [("Được mượn tối đa 5 cuốn trong 14 ngày.", 1.0)]
    assert check_question(q, CTX) is None
    assert finalize(q)["rubric"] == [{"point": "Được mượn tối đa 5 cuốn trong 14 ngày.", "weight": 1.0}]


@pytest.mark.parametrize("q", [
    _open("scenario", rubric=None),                                  # scenario: không tự bịa rubric
    _open("short_answer", rubric=None, answer="  "),                 # không có đáp án thì không có gì để làm ý
    _mcq(),                                                          # loại khác: không đụng tới
])
def test_ensure_rubric_leaves_other_questions_alone(q):
    before = q.rubric
    ensure_rubric(q)
    assert q.rubric == before


def test_ensure_rubric_keeps_existing_rubric():
    q = _open("short_answer")
    original = list(q.rubric)
    ensure_rubric(q)
    assert q.rubric == original


def test_number_rule_flags_computed_answer_and_can_be_disabled():
    q = _open(answer="Phạt 10.000 đồng cho 5 ngày trễ.")
    assert "10000" in (check_question(q, CTX) or "")
    assert check_question(q, CTX, reject_unverified_numbers=False) is None


def test_number_rule_for_mcq_only_looks_at_correct_option():
    # lựa chọn nhiễu có số lạ thì không sao; chỉ đáp án đúng bị kiểm
    ok = _mcq(options=["3 cuốn", "5 cuốn", "77 cuốn", "10 cuốn"])
    assert check_question(ok, CTX) is None
    bad = _mcq(options=["3 cuốn", "6 cuốn", "7 cuốn", "10 cuốn"], correct_index=1)
    assert "6" in (check_question(bad, CTX) or "")


def test_number_with_thousand_separator_matches_plain_number():
    q = _open(answer="Mỗi cuốn mỗi ngày phạt 2000 đồng.", source_quote=FINE_QUOTE)
    assert check_question(q, CTX) is None


def test_number_from_question_is_allowed():
    q = _open(question="Một sinh viên mượn 3 cuốn sách thì cần làm gì khi muốn gia hạn?",
              answer="Sinh viên mượn 3 cuốn và vẫn trong mức tối đa 5 cuốn.")
    assert check_question(q, CTX) is None


def test_grounded_requires_min_tokens_and_tolerates_small_edits():
    assert not grounded("quá ngắn", CTX)
    assert grounded(QUOTE, CTX)
    assert grounded(QUOTE.upper(), CTX)  # không phân biệt hoa thường
    # đổi 1/10 từ (90% < 92%) -> không đạt; đổi 1/13 từ (~92,3%) -> đạt
    ten = "Sinh viên được mượn tối đa 5 cuốn sách trong 14 ngày"
    assert not grounded(ten.replace("14", "99"), CTX)
    thirteen = "Sách trả trễ bị phạt 2.000 đồng cho mỗi cuốn mỗi ngày quá hạn"
    assert grounded(thirteen.replace("hạn", "xyz"), CTX)


def test_finalize_mcq_shuffles_deterministically_and_keeps_correct_letter():
    q = _mcq(options=["A. 3 cuốn", "B. 5 cuốn", "C. 7 cuốn", "D. 10 cuốn"])
    a, b = finalize(q), finalize(q)
    assert a == b  # xáo tất định theo nội dung câu hỏi
    assert sorted(a["options"]) == sorted(["3 cuốn", "5 cuốn", "7 cuốn", "10 cuốn"])  # đã bỏ tiền tố A./B.
    assert a["options"]["ABCD".index(a["answer"])] == "5 cuốn"


def test_finalize_rubric_weights_sum_to_exactly_one():
    q = _open(rubric=[{"point": "a", "weight": 1}, {"point": "b", "weight": 1}, {"point": "c", "weight": 1}])
    out = finalize(q)
    assert sum(r["weight"] for r in out["rubric"]) == pytest.approx(1.0, abs=1e-9)
    assert out["options"] is None


def test_finalize_zero_or_negative_weights_fall_back_to_equal():
    q = _open(rubric=[{"point": "a", "weight": 0}, {"point": "b", "weight": -2}])
    out = finalize(q)
    assert [r["weight"] for r in out["rubric"]] == [0.5, 0.5]


def test_finalize_fill_blank_keeps_clean_alt_answers():
    out = finalize(_fill(alt_answers=[" mười bốn ", "  "]))
    assert out["meta"]["alt_answers"] == ["mười bốn"]


# ---- Phép tính do LLM ghi trong "calculation" được code tính lại ----
FINE_Q = "Sinh viên A mượn 3 cuốn sách giáo trình và trả muộn 10 ngày. Sinh viên A phải trả bao nhiêu tiền phạt?"
FINE_QUOTE = "Sách trả trễ bị phạt 2.000 đồng cho mỗi cuốn mỗi ngày quá hạn."


def _fine(answer="Sinh viên A phải trả 60.000 đồng tiền phạt.", calc="3*10*2000", question=FINE_Q, qtype="short_answer"):
    return _open(qtype, question=question, answer=answer, calculation=calc, source_quote=FINE_QUOTE)


@pytest.mark.parametrize(("expr", "expected"), [
    ("3*10*2000", (60000, {"3", "10", "2000"})),
    ("3 × 10 × 2000", (60000, {"3", "10", "2000"})),
    ("3*10*2000 = 60000", (60000, {"3", "10", "2000"})),            # phần sau dấu = bị bỏ
    ("5*(21-14)*2000", (70000, {"5", "21", "14", "2000"})),
    ("100/4", (25, {"100", "4"})),
    ("-(-5)*2", (10, {"5", "2"})),
])
def test_eval_calculation_valid_expressions(expr, expected):
    from app.modules.generation.rules import eval_calculation

    assert eval_calculation(expr) == expected


@pytest.mark.parametrize("expr", [
    "", "abc", "3*", "__import__('os').system('x')", "2**100", "len('a')", "3*x", "10/4", "5-10", "0", "1/0",
    "2.5*2", "(1+1", "[1,2]", "1" * 120, "+".join(["1"] * 60), "+".join(["1"] * 25), "True+1", "3 and 4",
])
def test_eval_calculation_rejects_unsafe_or_unusable_expressions(expr):
    from app.modules.generation.rules import eval_calculation

    assert eval_calculation(expr) is None


def test_verified_calculation_lets_computed_answer_through():
    assert check_question(_fine(), CTX) is None
    assert check_question(_fine(qtype="scenario"), CTX) is None


def test_computed_answer_without_calculation_is_still_rejected():
    reason = check_question(_fine(calc=None), CTX) or ""
    assert "60000" in reason and "phép tính kèm theo" not in reason


@pytest.mark.parametrize(("kw", "why"), [
    ({"calc": "10*2000", "answer": "Phải trả 20.000 đồng."}, "quên số cuốn nêu trong câu hỏi"),
    ({"calc": "3*10*2000"}, None),                                        # đối chứng: đúng thì qua
    ({"calc": "3*10*2500"}, "toán hạng 2500 không có trong tài liệu"),
    ({"calc": "3*10*2000+0"}, "kết quả đúng nhưng toán hạng 0 không lấy từ tài liệu hay câu hỏi"),
    ({"calc": "6*10*1000"}, "kết quả đúng nhưng đi bằng số tự chọn và bỏ số nêu trong câu hỏi"),
    ({"calc": "3*10*2000", "answer": "Phải trả 50.000 đồng."}, "kết quả không khớp đáp án"),
    ({"calc": "3*10*2000", "answer": "Phải trả 60.000 đồng sau 99 ngày."}, "đáp án còn thêm số khác chưa kiểm chứng"),
    ({"calc": "2**9999999"}, "biểu thức nguy hiểm"),
    ({"calc": "garbage"}, "biểu thức hỏng"),
])
def test_calculation_must_prove_the_answer(kw, why):
    reason = check_question(_fine(**kw), CTX)
    if why is None:
        assert reason is None
    else:
        assert reason and "phép tính kèm theo không chứng minh được đáp án" in reason, why


def test_calculation_with_subtraction_using_numbers_from_context():
    q = _fine(question="Sinh viên B mượn 5 cuốn sách giáo trình và trả sau 21 ngày. Sinh viên B phải trả bao nhiêu tiền phạt?",
              answer="70.000 đồng", calc="5*(21-14)*2000")
    assert check_question(q, CTX) is None


def test_mcq_with_computed_correct_option_needs_calculation_too():
    opts = ["40.000 đồng", "50.000 đồng", "60.000 đồng", "80.000 đồng"]
    base = {"question": FINE_Q, "options": opts, "correct_index": 2, "answer": "60.000 đồng", "source_quote": FINE_QUOTE}
    assert check_question(_mcq(**base), CTX) is not None
    assert check_question(_mcq(**base, calculation="3*10*2000"), CTX) is None


def test_calculation_is_ignored_when_answer_has_no_new_number():
    assert check_question(_open(calculation="999*999"), CTX) is None  # không cần chứng minh nên không bị soi


@pytest.mark.parametrize(("raw", "expected"), [("3*10", "3*10"), ("  ", None), (None, None), (12, None), (["a"], None)])
def test_schema_coerces_calculation_field(raw, expected):
    assert _open(calculation=raw).calculation == expected


def test_finalize_keeps_calculation_in_meta_only_when_present():
    assert finalize(_fine())["meta"]["calculation"] == "3*10*2000"
    assert "calculation" not in finalize(_open())["meta"]


# ---- Số trong đáp án phải nằm trong source_quote (trích dẫn phải thật sự làm căn cứ) ----
DL_CTX = ("Sinh viên truy cập cơ sở dữ liệu điện tử bằng tài khoản của trường. Khi truy cập từ ngoài khuôn viên trường, sinh viên phải "
          "kết nối qua dịch vụ VPN của trường trước khi đăng nhập. Mỗi lượt tải toàn văn tài liệu điện tử không được vượt quá 50 trang.")
VPN_QUOTE = "Khi truy cập từ ngoài khuôn viên trường, sinh viên phải kết nối qua dịch vụ VPN của trường trước khi đăng nhập."
PAGES_QUOTE = "Mỗi lượt tải toàn văn tài liệu điện tử không được vượt quá 50 trang."


def _pages(quote):
    return _open("short_answer", question="Sinh viên cần tải một cuốn sách điện tử dài 70 trang. Sinh viên có tải được không?",
                 answer="Không, vì 70 trang vượt giới hạn 50 trang cho mỗi lượt tải.", source_quote=quote)


def test_answer_number_missing_from_quote_is_rejected_even_if_it_is_in_the_document():
    reason = check_question(_pages(VPN_QUOTE), DL_CTX) or ""
    assert "50" in reason and "không nằm trong source_quote" in reason


def test_same_question_passes_when_the_quote_actually_supports_the_answer():
    assert check_question(_pages(PAGES_QUOTE), DL_CTX) is None


def test_quote_support_check_can_be_disabled_with_the_numbers_flag():
    assert check_question(_pages(VPN_QUOTE), DL_CTX, reject_unverified_numbers=False) is None


def test_quote_support_check_applies_to_mcq_correct_option_and_fill_blank():
    mcq = _mcq(options=["3 cuốn", "5 cuốn", "7 cuốn", "10 cuốn"], source_quote="Thư viện mở cửa từ 7 giờ đến 20 giờ các ngày trong tuần.")
    assert "không nằm trong source_quote" in (check_question(mcq, CTX) or "")
    fill = _fill(source_quote="Thư viện mở cửa từ 7 giờ đến 20 giờ các ngày trong tuần.")
    assert "không nằm trong source_quote" in (check_question(fill, CTX) or "")


def test_computed_result_does_not_need_to_be_in_the_quote():
    assert check_question(_fine(), CTX) is None  # 60.000 chỉ có trong biểu thức đã được kiểm chứng

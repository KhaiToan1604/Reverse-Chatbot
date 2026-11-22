"""Các dạng phản hồi lệch của validator mà model nhỏ hay trả."""

import pytest

from app.modules.generation.validator import _as_items

OK = {"answerable": True, "answer_correct": True, "unambiguous": True}


@pytest.mark.parametrize(("res", "n", "expected_keys"), [
    ({"results": [{"index": 0, **OK}, {"index": 1, **OK}]}, 2, {0, 1}),
    ([{"index": 0, **OK}], 1, {0}),                                    # danh sách trần
    ({"results": {"0": OK, "1": OK}}, 2, {0, 1}),                      # results là dict khoá số
    (OK, 1, {0}),                                                      # một kết quả đơn, lô 1 câu
    ([OK, OK], 2, {0, 1}),                                             # thiếu index nhưng đủ số phần tử -> theo thứ tự
    ([{"index": "1", **OK}, {"index": "0", **OK}], 2, {0, 1}),         # index dạng chuỗi
])
def test_as_items_accepts_common_shapes(res, n, expected_keys):
    got = _as_items(res, n)
    assert got is not None and set(got) == expected_keys


@pytest.mark.parametrize(("res", "n"), [
    (OK, 2),                      # kết quả đơn nhưng lô nhiều câu: không đoán
    ([OK], 2),                    # thiếu index và sai số lượng: không đoán
    ({"foo": "bar"}, 1),
    ({"results": "text"}, 1),
    ([], 1),
    (["a", "b"], 2),
    (None, 1),
    (42, 1),
])
def test_as_items_refuses_to_guess(res, n):
    assert _as_items(res, n) is None


def test_as_items_bool_index_is_not_treated_as_integer():
    # True == 1 trong Python; không được coi là chỉ số câu số 1
    assert _as_items([{"index": True, **OK}], 1) == {0: {"index": True, **OK}}

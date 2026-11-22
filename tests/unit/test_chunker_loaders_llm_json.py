"""Các hàm thuần dễ vỡ nhất của đường nạp dữ liệu và đọc phản hồi LLM: chunker, loader, extract_json, complete_json."""

import io

import pytest

from app.modules.ingestion.chunker import chunk_text
from app.modules.ingestion.loaders import UnsupportedFormat, load_text
from app.modules.llm.base import LLMError, LLMProvider, extract_json

# ---------- chunker ----------


def _para(i: int, n: int = 60) -> str:
    return f"Đoạn {i}: " + " ".join(f"từ{j}" for j in range(n)) + "."


def test_chunks_never_exceed_max_chars_and_keep_heading():
    text = "# Mục A\n\n" + "\n\n".join(_para(i) for i in range(12))
    chunks = chunk_text(text, max_chars=400, overlap=60, min_chars=80)
    assert len(chunks) > 3
    assert all(len(c.text) <= 400 for c in chunks)
    assert {c.heading for c in chunks} == {"Mục A"}


def test_adjacent_chunks_overlap():
    text = "\n\n".join(_para(i) for i in range(6))
    chunks = chunk_text(text, max_chars=500, overlap=80, min_chars=80)
    assert len(chunks) >= 2
    for a, b in zip(chunks, chunks[1:], strict=False):
        tail_word = a.text.split()[-1]
        assert tail_word in b.text  # phần đuôi chunk trước được mang sang chunk sau


def test_no_overlap_when_disabled():
    text = "\n\n".join(_para(i) for i in range(6))
    chunks = chunk_text(text, max_chars=500, overlap=0, min_chars=80)
    assert not any(c.text.startswith("từ") for c in chunks)


def test_hidden_html_comments_are_not_knowledge():
    chunks = chunk_text("# T\n\nNội dung thật của mục này, đủ dài để thành một chunk hoàn chỉnh. <!-- bí mật nội bộ -->")
    assert chunks and all("bí mật" not in c.text for c in chunks)


def test_very_long_sentence_without_punctuation_is_hard_cut_on_word_boundary():
    word = "chữ"
    text = " ".join([word] * 400)  # một câu 1.600 ký tự, không dấu chấm
    chunks = chunk_text(text, max_chars=300, overlap=0, min_chars=20)
    assert len(chunks) >= 5 and all(len(c.text) <= 300 for c in chunks)
    assert all(not c.text.startswith("ữ") and not c.text.endswith("ch") for c in chunks)  # không cắt giữa từ


def test_short_trailing_chunk_is_merged_into_previous():
    body = _para(0, 90) + "\n\n" + "Câu cuối ngắn."
    chunks = chunk_text(body, max_chars=520, overlap=0, min_chars=80)
    assert "Câu cuối ngắn." in chunks[-1].text  # không bị bỏ rơi thành chunk riêng
    assert all(len(c.text) >= 80 for c in chunks)


def test_empty_and_whitespace_input_gives_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  \n") == []


def test_each_section_gets_its_own_heading():
    text = "# A\n\nNội dung của mục A đủ dài để giữ lại thành chunk riêng.\n\n# B\n\nNội dung của mục B cũng đủ dài để giữ lại."
    assert [c.heading for c in chunk_text(text)] == ["A", "B"]


# ---------- loaders ----------


def test_loader_reads_utf8_with_bom_and_utf16():
    s = "Thư viện mở cửa lúc 7 giờ sáng."
    assert load_text("a.txt", ("﻿" + s).encode("utf-8")) == s
    assert load_text("a.md", s.encode("utf-16")) == s


def test_loader_normalizes_decomposed_vietnamese_to_nfc():
    import unicodedata

    decomposed = unicodedata.normalize("NFD", "Sinh viên được mượn sách")
    assert load_text("a.txt", decomposed.encode("utf-8")) == "Sinh viên được mượn sách"


def test_loader_rejects_unknown_extension():
    with pytest.raises(UnsupportedFormat):
        load_text("a.exe", b"MZ")


def test_loader_pdf_without_text_layer_explains_ocr_needed():
    from pypdf import PdfWriter

    buf = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.write(buf)
    with pytest.raises(UnsupportedFormat, match="OCR"):
        load_text("scan.pdf", buf.getvalue())


def test_loader_docx_turns_heading_styles_into_markdown_headings():
    import docx

    d = docx.Document()
    d.add_heading("Nội quy mượn sách", level=1)
    d.add_paragraph("Sinh viên mượn tối đa 5 cuốn.")
    d.add_heading("Phạt", level=2)
    d.add_paragraph("Trả trễ bị phạt 2.000 đồng.")
    buf = io.BytesIO()
    d.save(buf)
    out = load_text("noi_quy.docx", buf.getvalue())
    assert "# Nội quy mượn sách" in out and "## Phạt" in out and "Trả trễ bị phạt" in out


# ---------- extract_json / complete_json ----------


@pytest.mark.parametrize(("raw", "expected"), [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Đây là kết quả:\n{"a": [1, 2]}\nHết.', {"a": [1, 2]}),
    ('[{"index": 0}, {"index": 1}]', [{"index": 0}, {"index": 1}]),
    ('Văn bản {không phải json} rồi {"ok": true}', {"ok": True}),
    ('{"s": "chuỗi có dấu } và \\" bên trong"}', {"s": 'chuỗi có dấu } và " bên trong'}),
])
def test_extract_json_tolerates_noise(raw, expected):
    assert extract_json(raw) == expected


@pytest.mark.parametrize("raw", ["", "không có json nào", '{"a": ', "[1, 2"])
def test_extract_json_raises_llm_error_on_garbage(raw):
    with pytest.raises(LLMError):
        extract_json(raw)


class _Scripted(LLMProvider):
    name = "scripted"

    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), 0

    def complete(self, system, user, *, json_mode=True, temperature=0.3):
        self.calls += 1
        return self.outputs.pop(0)


def test_complete_json_retries_once_then_succeeds():
    llm = _Scripted(["xin lỗi tôi không biết", '{"ok": 1}'])
    assert llm.complete_json("s", "u") == {"ok": 1} and llm.calls == 2


def test_complete_json_gives_up_after_retries():
    llm = _Scripted(["rác", "vẫn rác"])
    with pytest.raises(LLMError):
        llm.complete_json("s", "u", retries=1)
    assert llm.calls == 2


def test_complete_json_without_retries_calls_once():
    llm = _Scripted(["rác", '{"ok": 1}'])
    with pytest.raises(LLMError):
        llm.complete_json("s", "u", retries=0)
    assert llm.calls == 1


def test_tail_helper_edge_cases():
    from app.modules.ingestion.chunker import _tail

    assert _tail("một hai ba", 100) == "một hai ba"  # ngắn hơn n: giữ nguyên, không mất từ đầu
    assert _tail("một hai ba", 0) == ""
    assert _tail("một hai ba bốn năm", 9) == "bốn năm"  # bắt đầu ở ranh giới từ, không cắt giữa từ
    assert _tail("liềnmộtkhối", 5) == "tkhối"  # không có khoảng trắng: giữ nguyên n ký tự cuối

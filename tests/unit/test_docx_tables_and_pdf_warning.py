"""Bộ đọc .docx với bảng (ô gộp, tiêu đề hai tầng, cột STT) và cảnh báo PDF ít chữ."""

import io
import logging

import docx

from app.modules.ingestion.chunker import chunk_text
from app.modules.ingestion.loaders import load_text


def _docx_bytes(build) -> bytes:
    d = docx.Document()
    build(d)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _fill(table, rows):
    for r, values in enumerate(rows):
        for c, v in enumerate(values):
            table.cell(r, c).text = v


def test_simple_table_becomes_one_line_per_row_with_column_names():
    def build(d):
        t = d.add_table(rows=3, cols=3)
        _fill(t, [["Đối tượng", "Số cuốn", "Số ngày"], ["Sinh viên", "5", "21"], ["Khách", "2", "30"]])

    out = load_text("a.docx", _docx_bytes(build))
    assert "- Đối tượng: Sinh viên | Số cuốn: 5 | Số ngày: 21." in out
    assert "- Đối tượng: Khách | Số cuốn: 2 | Số ngày: 30." in out


def test_paragraphs_and_tables_keep_document_order():
    def build(d):
        d.add_heading("Mượn sách", level=1)
        d.add_paragraph("Đoạn trước bảng.")
        t = d.add_table(rows=2, cols=2)
        _fill(t, [["Loại", "Phí"], ["Thẻ", "45.000đ"]])
        d.add_paragraph("Đoạn sau bảng.")

    out = load_text("a.docx", _docx_bytes(build))
    assert out.index("# Mượn sách") < out.index("Đoạn trước") < out.index("Thẻ") < out.index("Đoạn sau")
    assert "Phí: 45.000đ" in out


def test_two_level_header_is_joined_and_vertical_merge_keeps_first_label():
    def build(d):
        t = d.add_table(rows=3, cols=3)
        _fill(t, [["Đối tượng", "Gia hạn", ""], ["", "Số lần", "Số ngày"], ["Sinh viên", "1", "21"]])
        t.cell(0, 1).merge(t.cell(0, 2))
        t.cell(0, 0).merge(t.cell(1, 0))

    out = load_text("a.docx", _docx_bytes(build))
    assert "- Đối tượng: Sinh viên | Gia hạn – Số lần: 1 | Gia hạn – Số ngày: 21." in out


def test_horizontally_merged_value_is_repeated_for_each_column():
    def build(d):
        t = d.add_table(rows=2, cols=3)
        _fill(t, [["Dịch vụ", "Trong trường", "Ngoài trường"], ["Scan", "1.000đ", ""]])
        t.cell(1, 1).merge(t.cell(1, 2))

    out = load_text("a.docx", _docx_bytes(build))
    assert "Trong trường: 1.000đ | Ngoài trường: 1.000đ" in out


def test_index_column_is_dropped_and_group_row_printed_plainly():
    def build(d):
        t = d.add_table(rows=3, cols=3)
        _fill(t, [["STT", "Nội dung", "Phí"], ["1", "Tiếp nhận", "Miễn phí"], ["2", "Dịch vụ cung cấp thông tin:", ""]])
        t.cell(2, 1).merge(t.cell(2, 2))

    out = load_text("a.docx", _docx_bytes(build))
    assert "STT" not in out
    assert "- Nội dung: Tiếp nhận | Phí: Miễn phí." in out
    assert "\n- Dịch vụ cung cấp thông tin:\n" in out


def test_one_row_or_one_column_table_is_plain_lines():
    def build(d):
        t = d.add_table(rows=2, cols=1)
        _fill(t, [["Dòng một"], ["Dòng hai"]])

    out = load_text("a.docx", _docx_bytes(build))
    assert "- Dòng một" in out and "- Dòng hai" in out


def test_empty_table_adds_nothing():
    def build(d):
        d.add_paragraph("Chỉ có đoạn.")
        d.add_table(rows=2, cols=2)

    assert load_text("a.docx", _docx_bytes(build)).strip() == "Chỉ có đoạn."


def test_table_rows_survive_chunking_as_whole_lines():
    def build(d):
        d.add_heading("Phí", level=1)
        t = d.add_table(rows=31, cols=2)
        _fill(t, [["Loại", "Mức phí"]] + [[f"Dịch vụ số {i}", f"{i}.000đ"] for i in range(1, 31)])

    chunks = chunk_text(load_text("a.docx", _docx_bytes(build)))
    assert len(chunks) > 1
    for c in chunks:
        assert all(line.endswith(".") for line in c.text.splitlines() if line.startswith("- "))  # không cắt giữa dòng


def _tiny_pdf() -> bytes:
    """PDF 1 trang chỉ có 'Xin chao', dựng đúng cấu trúc (có bảng tham chiếu xref) để pypdf đọc được."""
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length 41>>\nstream\nBT /F1 12 Tf 20 100 Td (Xin chao) Tj ET\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_pdf_with_very_little_text_loads_but_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="app.modules.ingestion.loaders"):
        out = load_text("tai_lieu.pdf", _tiny_pdf())
    assert "Xin chao" in out
    assert any("rất ít chữ" in r.message for r in caplog.records)

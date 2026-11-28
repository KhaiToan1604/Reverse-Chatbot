"""Đọc tài liệu nguồn thành văn bản thuần: .txt .md .pdf .docx

Được ingestion/service.py gọi. Muốn hỗ trợ định dạng mới (vd. .html): thêm đuôi vào `SUPPORTED`, thêm một nhánh
`if ext == ...` trong `load_text` trả về văn bản (nên dùng `#`/`##` cho tiêu đề để chunker chia mục đúng).

Điểm cần biết:
- .docx: đọc theo đúng thứ tự trong tài liệu, gồm cả đoạn văn lẫn BẢNG. Mỗi dòng của bảng được viết lại thành một dòng
  "- Tên cột: giá trị | Tên cột: giá trị" để khi chunker cắt thành mục riêng, dòng vẫn tự đủ nghĩa (xem `_table_to_lines`).
- .pdf: chỉ đọc được lớp chữ. PDF scan bị từ chối; PDF nhiều ảnh, ít chữ vẫn nạp nhưng có cảnh báo trong log."""

import io
import logging
from pathlib import Path

from app.common.text import nfc

log = logging.getLogger(__name__)

SUPPORTED = {".txt", ".md", ".pdf", ".docx"}  # router /documents và scripts/ingest.py dùng tập này để lọc file

# PDF có trung bình ít hơn số ký tự này mỗi trang thì ghi cảnh báo "nhiều ảnh, ít chữ" (không chặn việc nạp).
PDF_MIN_CHARS_PER_PAGE = 150

# Các tiêu đề cột chỉ là số thứ tự: bỏ khỏi dòng bảng vì chỉ gây nhiễu cho câu hỏi.
_INDEX_LABELS = {"stt", "tt", "số tt", "số thứ tự", "no", "no."}


class UnsupportedFormat(ValueError):
    """Định dạng không đọc được (API trả HTTP 415)."""

    pass


def _cell_text(cell) -> str:
    """Văn bản một ô: các đoạn trong ô nối bằng ' / ' (không dùng ';' vì chunker coi ';' là ranh giới câu)."""
    return " / ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())


def _table_to_lines(table) -> list[str]:
    """Viết một bảng Word thành các dòng '- Tên cột: giá trị | ...', mỗi dòng ứng với một hàng dữ liệu.

    - Ô gộp ngang/dọc được python-docx lặp lại ở mọi cột nó phủ, nên giá trị gộp (vd. "Miễn phí" cho cả hai nhóm độc giả)
      xuất hiện đủ ở từng cột.
    - Tiêu đề hai tầng (hàng 1 có ô gộp ngang, hàng 2 là cột con) được ghép thành "Gia hạn – Số lần".
    - Hàng mà cả hàng chỉ là một ô gộp (tiêu đề nhóm) được in nguyên văn không kèm tên cột.
    Bảng chỉ có một hàng hoặc một cột được in thành các dòng văn bản thường."""
    grid = []  # mỗi hàng: danh sách (id ô gốc, văn bản) theo cột lưới
    for row in table.rows:
        grid.append([(id(c._tc), _cell_text(c)) for c in row.cells])
    grid = [r for r in grid if any(t for _, t in r)]
    if not grid:
        return []
    ncols = len(grid[0])
    if len(grid) < 2 or ncols < 2:
        return [f"- {' | '.join(dict.fromkeys(t for _, t in r if t))}" for r in grid]

    # Hàng 2 là tiêu đề con nếu nó dùng chung ô (gộp dọc) hoặc cùng cột con với hàng 1 có ô gộp ngang.
    first_ids = [i for i, _ in grid[0]]
    has_h_span = len(set(first_ids)) < len(first_ids)
    shares_cell = bool({i for i, _ in grid[1]} & set(first_ids))
    header_rows = 2 if len(grid) > 2 and has_h_span and shares_cell else 1
    labels = []
    for col in range(ncols):
        top = grid[0][col][1]
        sub = grid[1][col][1] if header_rows == 2 else ""
        labels.append(top if not sub or sub == top else (sub if not top else f"{top} – {sub}"))

    lines: list[str] = []
    for row in grid[header_rows:]:
        # Bỏ cột số thứ tự; nếu phần còn lại chỉ là một ô gộp thì in nguyên văn.
        cells = [(rid, labels[c], t) for c, (rid, t) in enumerate(row) if t and labels[c].lower() not in _INDEX_LABELS]
        if not cells:
            continue
        single_merged_cell = len({rid for rid, _, _ in cells}) == 1
        line = cells[0][2] if single_merged_cell else " | ".join(f"{lab}: {t}" if lab else t for _, lab, t in cells)
        lines.append(f"- {line}" if line.endswith((".", "!", "?", "…", ":")) else f"- {line}.")
    return lines


def _docx_to_text(data: bytes) -> str:
    """Đọc .docx theo thứ tự xuất hiện: đoạn văn (tiêu đề -> '#') và bảng (-> các dòng '- cột: giá trị')."""
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(io.BytesIO(data))
    parts: list[str] = []
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(el, d)
            if not p.text.strip():
                parts.append("")
                continue
            style = (p.style.name or "").lower() if p.style is not None else ""
            if style == "title":
                parts.append(f"# {p.text.strip()}")
            elif style.startswith("heading"):
                level = "".join(c for c in style if c.isdigit()) or "1"
                parts.append(f"{'#' * min(int(level), 6)} {p.text.strip()}")
            else:
                parts.append(p.text.strip())
        elif tag == "tbl":
            lines = _table_to_lines(Table(el, d))
            if lines:  # bảng ngăn cách với đoạn trước/sau bằng dòng trống để chunker coi là một khối
                parts.extend(["", *lines, ""])
    return nfc("\n".join(parts))


def load_text(filename: str, data: bytes) -> str:
    """Giải mã nội dung `data` của tệp `filename` (nhận dạng theo đuôi file) thành văn bản NFC.

    .txt/.md thử lần lượt các bảng mã utf-8, utf-16, cp1258 (tiếng Việt cũ); .pdf cần có lớp chữ (PDF scan sẽ bị từ chối);
    .docx giữ tiêu đề dạng Heading thành dấu `#` và đọc cả bảng. Ném UnsupportedFormat nếu không đọc được."""
    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md"):
        for enc in ("utf-8-sig", "utf-16", "cp1258"):
            try:
                return nfc(data.decode(enc))
            except UnicodeError:
                continue
        return nfc(data.decode("utf-8", errors="replace"))
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages]
        text = "\n\n".join(pages)
        if not text.strip():
            raise UnsupportedFormat("PDF không có lớp văn bản (có thể là bản scan, cần OCR trước).")
        if len(text.strip()) / max(1, len(pages)) < PDF_MIN_CHARS_PER_PAGE:
            log.warning(
                "%s: PDF rất ít chữ (%d ký tự cho %d trang). Nếu tài liệu có nhiều ảnh thì nội dung trong ảnh KHÔNG được đọc; "
                "nên chuyển nội dung sang .md hoặc .docx.",
                filename, len(text.strip()), len(pages),
            )
        return nfc(text)
    if ext == ".docx":
        return _docx_to_text(data)
    raise UnsupportedFormat(f"Định dạng chưa hỗ trợ: {ext or filename}")

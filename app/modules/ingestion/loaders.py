"""Đọc tài liệu nguồn thành văn bản thuần: .txt .md .pdf .docx

Được ingestion/service.py gọi. Muốn hỗ trợ định dạng mới (vd. .html): thêm đuôi vào `SUPPORTED`, thêm một nhánh
`if ext == ...` trong `load_text` trả về văn bản (nên dùng `#`/`##` cho tiêu đề để chunker chia mục đúng)."""

import io
from pathlib import Path

from app.common.text import nfc

SUPPORTED = {".txt", ".md", ".pdf", ".docx"}  # router /documents và scripts/ingest.py dùng tập này để lọc file


class UnsupportedFormat(ValueError):
    """Định dạng không đọc được (API trả HTTP 415)."""

    pass


def load_text(filename: str, data: bytes) -> str:
    """Giải mã nội dung `data` của tệp `filename` (nhận dạng theo đuôi file) thành văn bản NFC.

    .txt/.md thử lần lượt các bảng mã utf-8, utf-16, cp1258 (tiếng Việt cũ); .pdf cần có lớp chữ (PDF scan sẽ bị từ chối);
    .docx giữ tiêu đề dạng Heading thành dấu `#`. Ném UnsupportedFormat nếu không đọc được."""
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
        return nfc(text)
    if ext == ".docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        parts: list[str] = []
        for p in d.paragraphs:
            if not p.text.strip():
                parts.append("")
                continue
            style = (p.style.name or "").lower() if p.style is not None else ""
            if style.startswith("heading"):
                level = "".join(c for c in style if c.isdigit()) or "1"
                parts.append(f"{'#' * min(int(level), 6)} {p.text.strip()}")
            else:
                parts.append(p.text.strip())
        return nfc("\n".join(parts))
    raise UnsupportedFormat(f"Định dạng chưa hỗ trợ: {ext or filename}")

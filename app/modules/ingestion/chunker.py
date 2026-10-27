"""Chia văn bản thành chunk theo cấu trúc: heading Markdown -> đoạn -> câu.

Mỗi chunk là một "đơn vị tri thức": vừa đủ nhỏ để sinh câu hỏi bám sát nguồn, và là đơn vị
theo dõi mức thành thạo (mastery) của người học.
"""

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
SENT_RE = re.compile(r"(?<=[.!?…;])\s+")


@dataclass
class RawChunk:
    heading: str
    text: str


def split_sections(text: str) -> list[tuple[str, str]]:
    """Tách theo heading Markdown. Heading con được nối: 'Cha > Con'."""
    sections: list[tuple[str, list[str]]] = []
    stack: list[tuple[int, str]] = []
    current_heading = ""
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append((current_heading, [body]))

    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            flush()
            buf = []
            level, title = len(m.group(1)), m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current_heading = " > ".join(t for _, t in stack)
        else:
            buf.append(line)
    flush()
    return [(h, b[0]) for h, b in sections]


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    out: list[str] = []
    cur = ""
    for sent in SENT_RE.split(paragraph):
        while len(sent) > max_chars:  # câu quá dài: cắt cứng theo từ
            cut = sent.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if cur:
                out.append(cur)
                cur = ""
            out.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if cur and len(cur) + 1 + len(sent) > max_chars:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def _tail(text: str, n: int) -> str:
    if n <= 0 or len(text) <= n:
        return "" if n <= 0 else text
    t = text[-n:]
    sp = t.find(" ")
    return t[sp + 1 :] if sp != -1 else t


def chunk_text(text: str, max_chars: int = 800, overlap: int = 100, min_chars: int = 80) -> list[RawChunk]:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)  # chú thích ẩn không phải tri thức
    chunks: list[RawChunk] = []
    for heading, body in split_sections(text):
        # đoạn = các dòng liền nhau; dòng trống ngăn cách. Danh sách (-, *, 1.) giữ cùng đoạn.
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        units: list[str] = []
        for p in paragraphs:
            units.extend(_split_long(re.sub(r"[ \t]+\n", "\n", p), max_chars))

        section_chunks: list[str] = []
        cur = ""
        for u in units:
            if cur and len(cur) + 2 + len(u) > max_chars:
                section_chunks.append(cur)
                carry = _tail(cur, overlap)
                cur = f"{carry}\n\n{u}" if carry and len(carry) + 2 + len(u) <= max_chars else u
            else:
                cur = f"{cur}\n\n{u}" if cur else u
        if cur:
            section_chunks.append(cur)

        # gộp chunk cuối quá ngắn vào chunk trước (cùng section)
        if len(section_chunks) > 1 and len(section_chunks[-1]) < min_chars:
            section_chunks[-2] = f"{section_chunks[-2]}\n\n{section_chunks.pop()}"
        chunks.extend(RawChunk(heading, c) for c in section_chunks if len(c.strip()) >= min(min_chars, 20))
    return chunks

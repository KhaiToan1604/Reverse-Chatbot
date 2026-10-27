"""Định dạng các phần có đánh dấu trong prompt.

Prompt dùng các khối `<<<NAME>>> ... <<<END>>>` để tách rõ dữ liệu (tài liệu, câu trả lời của
người dùng) khỏi chỉ dẫn. MockLLM cũng parse ngược các khối này để chạy offline.
"""

import re


def section(name: str, content: str) -> str:
    # Chặn nội dung giả mạo marker (prompt injection từ tài liệu / câu trả lời người dùng)
    safe = content.replace("<<<", "< < <").replace(">>>", "> > >")
    return f"<<<{name}>>>\n{safe}\n<<<END>>>"


def get_section(text: str, name: str) -> str | None:
    m = re.search(rf"<<<{re.escape(name)}>>>\n(.*?)\n<<<END>>>", text, re.S)
    return m.group(1) if m else None

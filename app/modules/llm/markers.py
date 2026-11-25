"""Định dạng các phần có đánh dấu trong prompt.

Prompt dùng các khối `<<<NAME>>> ... <<<END>>>` để tách rõ dữ liệu (tài liệu, câu trả lời của
người dùng) khỏi chỉ dẫn. MockLLM cũng parse ngược các khối này để chạy offline.
"""

import re


def section(name: str, content: str) -> str:
    """Bọc `content` thành khối `<<<NAME>>>\\n...\\n<<<END>>>` để đưa vào prompt.

    Mọi dữ liệu không đáng tin (văn bản tài liệu, câu trả lời của người học) phải đi qua hàm này.
    """
    # Chặn nội dung giả mạo marker (prompt injection từ tài liệu / câu trả lời người dùng)
    # Chèn khoảng trắng để "<<<END>>>" nằm trong dữ liệu không còn khớp, nên không thể đóng khối sớm.
    safe = content.replace("<<<", "< < <").replace(">>>", "> > >")
    return f"<<<{name}>>>\n{safe}\n<<<END>>>"


def get_section(text: str, name: str) -> str | None:
    """Lấy nội dung khối `name` từ prompt (ngược lại với `section`); None nếu không có. Chủ yếu dùng cho MockLLM."""
    m = re.search(rf"<<<{re.escape(name)}>>>\n(.*?)\n<<<END>>>", text, re.S)
    return m.group(1) if m else None

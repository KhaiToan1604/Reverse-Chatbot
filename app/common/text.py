"""Chuẩn hoá chuỗi tiếng Việt dùng chung cho chấm điểm và so khớp (loader, rules, grading gọi vào đây).

Các chuỗi tiếng Việt có thể ở dạng NFC (chữ có dấu là một ký tự) hoặc NFD (chữ + dấu rời); luôn đưa về NFC trước khi so sánh.
"""

import re
import unicodedata


def nfc(s: str) -> str:
    """Đưa chuỗi về dạng Unicode NFC để cùng một chữ luôn có cùng một mã."""
    return unicodedata.normalize("NFC", s)


def strip_accents(s: str) -> str:
    """Bỏ toàn bộ dấu thanh và dấu mũ; `đ`/`Đ` không phân rã được nên được đổi riêng thành `d`/`D`."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def norm_text(s: str) -> str:
    """Chữ thường, bỏ dấu câu, gộp khoảng trắng — GIỮ dấu tiếng Việt."""
    s = nfc(s).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_loose(s: str) -> str:
    """Như norm_text nhưng bỏ cả dấu tiếng Việt (chịu được người dùng gõ không dấu)."""
    return norm_text(strip_accents(s))


def tokens(s: str) -> list[str]:
    """Tách thành danh sách từ (âm tiết) sau khi chuẩn hoá bằng `norm_text`."""
    return norm_text(s).split()

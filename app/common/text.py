import re
import unicodedata


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def strip_accents(s: str) -> str:
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
    return norm_text(s).split()

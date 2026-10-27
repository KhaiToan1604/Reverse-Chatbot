"""Chấm xấp xỉ bằng độ phủ từ khoá — dùng làm phương án dự phòng khi LLM lỗi, và cho MockLLM."""

from app.common.text import norm_loose

STOP = {"la", "va", "cua", "cho", "cac", "mot", "nhung", "duoc", "khi", "thi", "ma", "den", "trong", "voi", "o", "tai", "de", "co", "se", "phai", "nay", "do"}


def _content_tokens(s: str) -> set[str]:
    return {t for t in norm_loose(s).split() if t not in STOP and len(t) > 1}


def point_covered(point: str, answer: str, threshold: float = 0.5) -> bool:
    p = _content_tokens(point)
    if not p:
        return False
    return len(p & _content_tokens(answer)) / len(p) >= threshold

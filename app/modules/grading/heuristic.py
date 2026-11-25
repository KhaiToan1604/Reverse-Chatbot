"""Chấm xấp xỉ bằng độ phủ từ khoá — dùng làm phương án dự phòng khi LLM lỗi, và cho MockLLM."""

from app.common.text import norm_loose

# Từ nối/hư từ tiếng Việt (đã bỏ dấu, vì so khớp dùng norm_loose) bị bỏ qua khi đếm độ phủ. Thêm từ vào đây nếu thấy từ vô nghĩa làm lệch điểm.
STOP = {"la", "va", "cua", "cho", "cac", "mot", "nhung", "duoc", "khi", "thi", "ma", "den", "trong", "voi", "o", "tai", "de", "co", "se", "phai", "nay", "do"}


def _content_tokens(s: str) -> set[str]:
    """Tập từ có nghĩa của `s`: bỏ dấu, bỏ từ trong STOP và từ một ký tự."""
    return {t for t in norm_loose(s).split() if t not in STOP and len(t) > 1}


def point_covered(point: str, answer: str, threshold: float = 0.5) -> bool:
    """True nếu câu trả lời `answer` chứa ít nhất `threshold` (mặc định 50%) số từ có nghĩa của ý rubric `point`.

    Xấp xỉ thô: không hiểu đồng nghĩa hay phủ định. Chỉ dùng khi LLM không chấm được (xem llm_grader.py) và trong MockLLM.
    """
    p = _content_tokens(point)
    if not p:
        return False
    return len(p & _content_tokens(answer)) / len(p) >= threshold

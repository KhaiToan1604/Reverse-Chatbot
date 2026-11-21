"""Chấm bằng luật cho câu đóng (trắc nghiệm, điền khuyết): nhanh, miễn phí, kết quả ổn định."""

from difflib import SequenceMatcher

from app.common.text import norm_loose, norm_text
from app.db.models import Question
from app.modules.grading.schemas import GradeResult


def grade_mcq(q: Question, answer: str) -> GradeResult:
    """Chấp nhận đáp án là chữ cái ("B", "b)", "B. ...") hoặc gõ lại đúng nội dung lựa chọn."""
    a = answer.strip()
    letter = None
    m = norm_text(a)
    # Ký tự đầu là a-d và theo sau không phải chữ/số (tránh nhầm từ như "bao" với đáp án B).
    if m[:1] in "abcd" and (len(m) == 1 or (len(m) > 1 and not m[1].isalnum())):
        letter = m[0].upper()
    if letter is None and q.options:  # người dùng gõ nội dung lựa chọn
        for i, opt in enumerate(q.options):
            if norm_text(opt) == m:
                letter = "ABCD"[i]
                break
    correct = letter == q.answer
    # Đáp án đúng do API trả riêng ở reference_answer; feedback không lặp lại để giao diện khỏi hiển thị hai lần.
    return GradeResult(
        score=1.0 if correct else 0.0,
        is_correct=correct,
        feedback="Chính xác." if correct else "Chưa chính xác.",
        graded_by="rule",
    )


def match_fill_blank(q: Question, answer: str, fuzzy_threshold: float) -> tuple[bool, float]:
    """Trả về (khớp?, độ giống tốt nhất). So với đáp án chuẩn và các đáp án thay thế (alt_answers)."""
    cands = [q.answer, *((q.meta or {}).get("alt_answers") or [])]
    best = 0.0
    a_strict, a_loose = norm_text(answer), norm_loose(answer)
    for c in cands:
        if not a_strict:
            break
        if norm_text(c) == a_strict or norm_loose(c) == a_loose:  # khớp tuyệt đối / chấp nhận gõ không dấu
            return True, 1.0
        # độ giống ký tự (0..1) để chấp nhận lỗi gõ nhỏ; đạt khi >= fuzzy_threshold
        best = max(best, SequenceMatcher(None, norm_loose(c), a_loose).ratio())
    return best >= fuzzy_threshold, best


def grade_fill_blank_rule(q: Question, answer: str, fuzzy_threshold: float) -> GradeResult | None:
    """None = chưa kết luận được bằng luật (để LLM xem xét đồng nghĩa)."""
    ok, _ = match_fill_blank(q, answer, fuzzy_threshold)
    if ok:
        return GradeResult(1.0, True, "Chính xác.", [], "rule")
    return None

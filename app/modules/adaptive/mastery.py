"""Mô hình người học: mức nắm vững (EMA) và lịch ôn lại (Leitner đơn giản).

Chỉ có hai hàm đơn giản, không đụng DB hay mạng; gọi từ modules/quiz/service.py sau mỗi lần chấm điểm.
Muốn đổi cách tính (vd. dùng mô hình quên Ebbinghaus): sửa `apply_attempt`; các tham số nằm ở app/config.py
(MASTERY_ALPHA, REVIEW_INTERVALS_HOURS, APPLY_LEVEL_MASTERY, PASS_THRESHOLD).
"""

from datetime import datetime, timedelta

from app.config import Settings
from app.db.models import Mastery


def apply_attempt(m: Mastery, score: float, now: datetime, s: Settings) -> Mastery:
    """Cập nhật mức thành thạo sau một lần trả lời.

    - mastery: trung bình trượt mũ (EMA) của điểm -> phản ứng nhanh nhưng không giật.
    - streak + khoảng ôn: kiểu Leitner đơn giản; sai thì streak về 0 và cần ôn lại ngay.
    """
    correct = score >= s.pass_threshold
    # EMA: mastery_mới = mastery_cũ + alpha * (điểm - mastery_cũ). Mastery bắt đầu từ 0 khi chưa có bản ghi.
    m.mastery = round((m.mastery or 0.0) + s.mastery_alpha * (score - (m.mastery or 0.0)), 4)
    # streak = số lần đạt liên tiếp; sai một lần là về 0.
    m.streak = (m.streak or 0) + 1 if correct else 0
    m.correct_count = (m.correct_count or 0) + (1 if correct else 0)
    m.wrong_count = (m.wrong_count or 0) + (0 if correct else 1)
    m.last_seen = now
    # streak càng cao thì khoảng ôn càng dài; vượt độ dài danh sách thì dùng khoảng cuối cùng.
    intervals = s.review_intervals_hours
    m.due_at = now + timedelta(hours=intervals[min(m.streak, len(intervals) - 1)])
    return m


def desired_level(m: Mastery | None, s: Settings) -> str:
    """Chưa nắm vững -> hỏi nhớ thông tin; đã khá vững -> chuyển sang vận dụng."""
    return "apply" if m is not None and m.mastery >= s.apply_level_mastery else "recall"

"""Kết quả chấm điểm dùng chung cho mọi bộ chấm."""

from dataclasses import dataclass, field


@dataclass
class GradeResult:
    """Kết quả chấm một câu trả lời.

    `missing_points` là các ý còn thiếu (câu mở) hoặc đáp án chuẩn (điền khuyết không khớp) để hiển thị phản hồi;
    câu trắc nghiệm để trống (đáp án đúng do API trả riêng).
    """

    score: float  # 0..1
    is_correct: bool
    feedback: str = ""
    missing_points: list[str] = field(default_factory=list)
    # Ai chấm: rule = luật; llm = LLM xác nhận từng ý rubric; fallback = chấm từ khoá vì LLM lỗi (kém tin cậy, giao diện nên cảnh báo).
    graded_by: str = "rule"

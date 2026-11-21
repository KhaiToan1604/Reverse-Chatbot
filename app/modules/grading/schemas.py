"""Kết quả chấm điểm dùng chung cho mọi bộ chấm."""

from dataclasses import dataclass, field


@dataclass
class GradeResult:
    """`missing_points` là các ý còn thiếu (câu mở) hoặc đáp án đúng (câu đóng) để hiển thị phản hồi."""

    score: float  # 0..1
    is_correct: bool
    feedback: str = ""
    missing_points: list[str] = field(default_factory=list)
    graded_by: str = "rule"  # rule | llm | fallback

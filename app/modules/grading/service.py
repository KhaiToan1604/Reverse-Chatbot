"""Chọn cách chấm theo loại câu hỏi: trắc nghiệm/điền khuyết bằng luật, câu mở bằng rubric + LLM."""

from app.config import Settings
from app.db.models import Question
from app.modules.grading.llm_grader import LLMGrader
from app.modules.grading.rule_based import (
    grade_fill_blank_rule,
    grade_mcq,
)
from app.modules.grading.schemas import GradeResult
from app.modules.llm.base import LLMProvider


class GradingService:
    """Điểm vào duy nhất của việc chấm; QuizService chỉ cần gọi `grade`."""

    def __init__(self, settings: Settings, llm: LLMProvider):
        """Dùng các ngưỡng trong Settings: pass_threshold, fuzzy_threshold, llm_fallback_for_fill_blank."""
        self.s = settings
        self.llm_grader = LLMGrader(llm, settings.pass_threshold)

    def grade(self, q: Question, answer: str) -> GradeResult:
        """Chấm `answer` cho câu `q` theo loại câu; trả về GradeResult (câu trả lời rỗng cho 0 điểm, không gọi LLM).

        Thêm loại câu mới: thêm nhánh `if q.qtype == ...` ở đây (và thêm vào QTYPES trong generation/schemas.py).
        """
        if not answer or not answer.strip():
            return GradeResult(0.0, False, "Bạn chưa nhập câu trả lời.", [q.answer] if q.qtype != "mcq" else [], "rule")

        if q.qtype == "mcq":
            return grade_mcq(q, answer)

        # Điền khuyết: luật trước (nhanh, miễn phí); không khớp mới nhờ LLM xét cách nói đồng nghĩa.
        if q.qtype == "fill_blank":
            res = grade_fill_blank_rule(q, answer, self.s.fuzzy_threshold)
            if res:
                return res
            if self.s.llm_fallback_for_fill_blank:  # có thể là cách nói đồng nghĩa
                r = self.llm_grader.grade(q, answer, rubric=[{"point": q.answer, "weight": 1.0}])
                if not r.is_correct:
                    r.feedback = "Chưa chính xác."
                return r
            return GradeResult(0.0, False, "Chưa chính xác.", [q.answer], "rule")

        return self.llm_grader.grade(q, answer)  # short_answer / scenario

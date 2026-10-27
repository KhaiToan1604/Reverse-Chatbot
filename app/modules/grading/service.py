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
    def __init__(self, settings: Settings, llm: LLMProvider):
        self.s = settings
        self.llm_grader = LLMGrader(llm, settings.pass_threshold)

    def grade(self, q: Question, answer: str) -> GradeResult:
        if not answer or not answer.strip():
            return GradeResult(0.0, False, "Bạn chưa nhập câu trả lời.", [q.answer] if q.qtype != "mcq" else [], "rule")

        if q.qtype == "mcq":
            return grade_mcq(q, answer)

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

        return self.llm_grader.grade(q, answer)

import logging

from app.db.models import Question
from app.modules.grading.heuristic import point_covered
from app.modules.grading.prompts import build_grade_prompt
from app.modules.grading.schemas import GradeResult
from app.modules.llm.base import LLMError, LLMProvider

log = logging.getLogger(__name__)
MAX_ANSWER_CHARS = 2000


class LLMGrader:
    """Chấm tự luận theo rubric. LLM chỉ quyết định từng ý có được nêu hay không;
    điểm số được tính bằng code (tổng trọng số các ý đạt) nên ổn định và giải thích được."""

    def __init__(self, llm: LLMProvider, pass_threshold: float):
        self.llm = llm
        self.pass_threshold = pass_threshold

    def grade(self, q: Question, answer: str, rubric: list[dict] | None = None) -> GradeResult:
        rubric = rubric or q.rubric or [{"point": q.answer, "weight": 1.0}]
        student = answer.strip()[:MAX_ANSWER_CHARS]
        system, user = build_grade_prompt(q.question, q.answer, rubric, student)
        covered: list[bool] | None = None
        feedback = ""
        graded_by = "llm"
        try:
            res = self.llm.complete_json(system, user, temperature=0.0)
            cov = res.get("covered") if isinstance(res, dict) else None
            if isinstance(cov, list) and len(cov) == len(rubric):
                covered = [bool(x) for x in cov]
                feedback = str(res.get("feedback", "")).strip()
        except LLMError as e:
            log.warning("LLM grader lỗi, dùng heuristic: %s", e)

        if covered is None:
            graded_by = "fallback"
            covered = [point_covered(r["point"], student) for r in rubric]
            feedback = "(Chấm tự động bằng từ khoá do hệ thống chấm bằng AI tạm lỗi; kết quả có thể kém chính xác.)"

        total = sum(r["weight"] for r in rubric) or 1.0
        score = round(sum(r["weight"] for r, c in zip(rubric, covered) if c) / total, 4)
        missing = [r["point"] for r, c in zip(rubric, covered) if not c]
        return GradeResult(score, score >= self.pass_threshold, feedback, missing, graded_by)

from dataclasses import dataclass, field


@dataclass
class GradeResult:
    score: float  # 0..1
    is_correct: bool
    feedback: str = ""
    missing_points: list[str] = field(default_factory=list)
    graded_by: str = "rule"  # rule | llm | fallback

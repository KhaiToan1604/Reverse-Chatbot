from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, field_validator

QTYPES = ("mcq", "fill_blank", "short_answer", "scenario")
LEVELS = ("recall", "apply")


@dataclass
class Spec:
    qtype: str
    level: str
    count: int = 1


def default_specs() -> list[Spec]:
    """Hai mức theo đề bài: nhớ thông tin (recall) và vận dụng tình huống/quy trình (apply)."""
    return [
        Spec("mcq", "recall"),
        Spec("fill_blank", "recall"),
        Spec("scenario", "apply"),
        Spec("short_answer", "apply"),
    ]


class RubricItem(BaseModel):
    point: str
    weight: float = 1.0


class RawQuestion(BaseModel):
    """Một câu hỏi do LLM sinh ra, trước khi kiểm tra."""

    model_config = ConfigDict(extra="ignore")

    qtype: str
    level: str = "recall"
    question: str
    options: list[str] | None = None
    correct_index: int | None = None
    answer: str = ""
    alt_answers: list[str] = []
    rubric: list[RubricItem] | None = None
    explanation: str = ""
    source_quote: str = ""

    @field_validator("rubric", mode="before")
    @classmethod
    def _coerce_rubric(cls, v):
        if v is None:
            return None
        out = []
        for item in v:
            out.append({"point": item} if isinstance(item, str) else item)
        return out

    @field_validator("alt_answers", mode="before")
    @classmethod
    def _coerce_alt(cls, v):
        if v is None:
            return []
        return [v] if isinstance(v, str) else v

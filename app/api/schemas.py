from pydantic import BaseModel, Field

from app.modules.generation.schemas import LEVELS, QTYPES


class TextIngestIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=20)


class SpecIn(BaseModel):
    qtype: str
    level: str
    count: int = Field(default=1, ge=1, le=5)

    def validate_values(self) -> None:
        if self.qtype not in QTYPES or self.level not in LEVELS:
            raise ValueError(f"qtype phải thuộc {QTYPES}, level thuộc {LEVELS}")


class GenerateIn(BaseModel):
    document_id: int | None = None
    chunk_id: int | None = None
    specs: list[SpecIn] | None = None


class UserIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class SessionIn(BaseModel):
    user_id: int
    num_questions: int = Field(default=5, ge=1, le=30)
    document_id: int | None = None


class AnswerIn(BaseModel):
    question_id: int
    answer: str = Field(default="", max_length=5000)

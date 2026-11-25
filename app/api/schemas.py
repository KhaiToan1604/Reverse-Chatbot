"""Định dạng dữ liệu gửi lên API và giới hạn hợp lệ (Pydantic tự trả 422 nếu vi phạm)."""

from pydantic import BaseModel, Field

from app.modules.generation.schemas import LEVELS, QTYPES


class TextIngestIn(BaseModel):
    """Nạp tài liệu từ văn bản dán trực tiếp (POST /documents/text): `title` bắt buộc, `text` tối thiểu 20 ký tự."""

    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=20)


class SpecIn(BaseModel):
    """Yêu cầu sinh: loại câu hỏi + mức nhận thức + số lượng. Giá trị hợp lệ kiểm bằng validate_values."""

    qtype: str
    level: str
    count: int = Field(default=1, ge=1, le=5)

    def validate_values(self) -> None:
        """Ném ValueError nếu loại câu/mức không nằm trong danh sách hỗ trợ (router đổi thành HTTP 422)."""
        if self.qtype not in QTYPES or self.level not in LEVELS:
            raise ValueError(f"qtype phải thuộc {QTYPES}, level thuộc {LEVELS}")


class GenerateIn(BaseModel):
    """Sinh câu hỏi cho một chunk hoặc cả tài liệu; bỏ `specs` thì dùng bộ mặc định."""

    document_id: int | None = None
    chunk_id: int | None = None
    specs: list[SpecIn] | None = None


class UserIn(BaseModel):
    """Tạo người học (POST /users): chưa có đăng nhập thật, chỉ cần tên hiển thị."""

    display_name: str = Field(min_length=1, max_length=100)


class SessionIn(BaseModel):
    """Bắt đầu phiên học (POST /quiz/sessions): 1 đến 30 câu; bỏ `document_id` = học trên mọi tài liệu."""

    user_id: int
    num_questions: int = Field(default=5, ge=1, le=30)
    document_id: int | None = None


class AnswerIn(BaseModel):
    """Nộp đáp án (POST /quiz/sessions/{id}/answer): `question_id` phải là câu hiện tại của phiên; câu trả lời tối đa 5000 ký tự."""

    question_id: int
    answer: str = Field(default="", max_length=5000)

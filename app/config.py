"""Toàn bộ cấu hình, đọc từ biến môi trường hoặc file .env (tên biến = tên trường, viết hoa).

Muốn thêm một tuỳ chọn mới: thêm trường vào `Settings` và ghi vào .env.example.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình ứng dụng; `extra="ignore"` để biến môi trường lạ không gây lỗi."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Reverse Chatbot"
    admin_api_key: str = ""  # nếu đặt, các endpoint quản trị yêu cầu header X-Admin-Key
    cors_origins: list[str] = ["*"]
    frontend_dist: str = "./frontend/dist"  # nếu thư mục tồn tại, backend phục vụ luôn giao diện đã build
    database_url: str = "sqlite:///./data/app.db"
    vector_store_path: str = "./data/vectors"

    # LLM: "mock" chạy offline; "gemini" và "openai_compat" (Groq, Ollama...) gọi dịch vụ thật.
    llm_provider: Literal["mock", "gemini", "openai_compat"] = "mock"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 3
    # Giãn cách tối thiểu (giây) giữa hai lần gọi LLM để không vượt giới hạn phút của gói miễn phí
    # (ví dụ Gemini free ~10 lần/phút -> đặt 6). 0 = không giãn.
    llm_min_interval_s: float = 0.0

    # Embedding: "hashing" chỉ để dev/test; chạy thật dùng "sentence_transformers".
    embedding_provider: Literal["hashing", "sentence_transformers"] = "hashing"
    embedding_model: str = "BAAI/bge-m3"

    # Chunking: kích thước tối đa, phần chồng lấn giữa hai chunk liền kề, và độ dài tối thiểu (ký tự).
    chunk_max_chars: int = 800
    chunk_overlap_chars: int = 100
    chunk_min_chars: int = 80

    # Generation: có kiểm định bằng LLM không; ngưỡng cosine coi là câu trùng; số chunk lân cận làm ngữ cảnh;
    # có sinh thêm câu hỏi ngay khi người học hết câu trong ngân hàng không.
    validate_questions: bool = True
    # Loại câu có đáp án chứa số tự tính (không có trong tài liệu): model nhỏ hay sai phép tính. Xem rules.check_question.
    reject_unverified_numbers: bool = True
    dedup_threshold: float = 0.92
    retrieval_top_k: int = 2
    generate_on_demand: bool = True

    # Grading: điểm tối thiểu để tính là đạt; ngưỡng so khớp gần đúng cho điền khuyết;
    # cho phép nhờ LLM chấm lại khi điền khuyết không khớp luật (đồng nghĩa).
    pass_threshold: float = 0.6
    fuzzy_threshold: float = 0.85
    llm_fallback_for_fill_blank: bool = True

    # Adaptive learning: mastery_alpha là hệ số làm mượt EMA (càng lớn càng nhạy với kết quả mới nhất).
    mastery_alpha: float = 0.4
    apply_level_mastery: float = 0.6  # mastery >= ngưỡng này thì chuyển sang câu mức vận dụng
    # khoảng ôn lại (giờ) theo số lần đúng liên tiếp (Leitner đơn giản)
    review_intervals_hours: list[float] = [0, 4, 24, 72, 168, 336]


@lru_cache  # đọc một lần cho cả tiến trình
def get_settings() -> Settings:
    return Settings()

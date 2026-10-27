from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Reverse Chatbot"
    admin_api_key: str = ""  # nếu đặt, các endpoint quản trị yêu cầu header X-Admin-Key
    cors_origins: list[str] = ["*"]
    frontend_dist: str = "./frontend/dist"  # nếu thư mục tồn tại, backend phục vụ luôn giao diện đã build
    database_url: str = "sqlite:///./data/app.db"
    vector_store_path: str = "./data/vectors"

    # LLM
    llm_provider: Literal["mock", "gemini", "openai_compat"] = "mock"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 3

    # Embedding
    embedding_provider: Literal["hashing", "sentence_transformers"] = "hashing"
    embedding_model: str = "BAAI/bge-m3"

    # Chunking
    chunk_max_chars: int = 800
    chunk_overlap_chars: int = 100
    chunk_min_chars: int = 80

    # Generation
    validate_questions: bool = True
    dedup_threshold: float = 0.92
    retrieval_top_k: int = 2
    generate_on_demand: bool = True

    # Grading
    pass_threshold: float = 0.6
    fuzzy_threshold: float = 0.85
    llm_fallback_for_fill_blank: bool = True

    # Adaptive learning
    mastery_alpha: float = 0.4
    apply_level_mastery: float = 0.6  # mastery >= ngưỡng này thì chuyển sang câu mức vận dụng
    # khoảng ôn lại (giờ) theo số lần đúng liên tiếp (Leitner đơn giản)
    review_intervals_hours: list[float] = [0, 4, 24, 72, 168, 336]


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Toàn bộ cấu hình, đọc từ biến môi trường hoặc file .env (tên biến = tên trường, viết hoa).

Ví dụ: trường `llm_provider` được đặt bằng biến `LLM_PROVIDER`. Thứ tự ưu tiên: biến môi trường thật > file .env > giá trị
mặc định bên dưới. Mặc định chạy được offline (LLM giả + embedding băm); chạy thật thì chỉnh .env.

Muốn thêm một tuỳ chọn mới: thêm trường vào `Settings` và ghi vào .env.example.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình ứng dụng; `extra="ignore"` để biến môi trường lạ không gây lỗi."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Reverse Chatbot"  # APP_NAME: tiêu đề hiện ở trang tài liệu API (/docs)
    admin_api_key: str = ""  # nếu đặt, các endpoint quản trị yêu cầu header X-Admin-Key
    cors_origins: list[str] = ["*"]  # CORS_ORIGINS: nguồn được gọi API từ trình duyệt; khi triển khai thật nên giới hạn lại
    frontend_dist: str = "./frontend/dist"  # nếu thư mục tồn tại, backend phục vụ luôn giao diện đã build
    database_url: str = "sqlite:///./data/app.db"  # DATABASE_URL: SQLAlchemy URL; đổi sang PostgreSQL chỉ cần đổi chuỗi này
    vector_store_path: str = "./data/vectors"  # VECTOR_STORE_PATH: thư mục lưu vector; ":memory:" = chỉ giữ trong RAM

    # LLM: "mock" chạy offline; "gemini" và "openai_compat" (Groq, Ollama...) gọi dịch vụ thật.
    llm_provider: Literal["mock", "gemini", "openai_compat"] = "mock"
    llm_model: str = ""  # LLM_MODEL: tên model của nhà cung cấp (vd. gemini-3.5-flash, qwen2.5:7b)
    llm_api_key: str = ""  # LLM_API_KEY: khoá API (Ollama chạy local thì để trống)
    llm_base_url: str = ""  # LLM_BASE_URL: bắt buộc với openai_compat (vd. https://api.groq.com/openai/v1)
    llm_timeout_s: float = 60.0  # LLM_TIMEOUT_S: quá thời gian này một lần gọi bị coi là lỗi
    llm_max_retries: int = 3  # LLM_MAX_RETRIES: số lần thử lại khi gặp lỗi tạm thời (429, 5xx)
    # Giãn cách tối thiểu (giây) giữa hai lần gọi LLM để không vượt giới hạn phút của gói miễn phí
    # (ví dụ Gemini free ~10 lần/phút -> đặt 6). 0 = không giãn.
    llm_min_interval_s: float = 0.0

    # Embedding: "hashing" chỉ để dev/test; chạy thật dùng "sentence_transformers".
    embedding_provider: Literal["hashing", "sentence_transformers"] = "hashing"
    embedding_model: str = "BAAI/bge-m3"  # EMBEDDING_MODEL: chỉ dùng khi embedding_provider = sentence_transformers

    # Chunking: kích thước tối đa, phần chồng lấn giữa hai chunk liền kề, và độ dài tối thiểu (ký tự).
    chunk_max_chars: int = 800  # CHUNK_MAX_CHARS: nhỏ hơn -> nhiều mục, câu hỏi bám sát hơn nhưng thiếu ngữ cảnh
    chunk_overlap_chars: int = 100  # CHUNK_OVERLAP_CHARS: số ký tự lặp lại giữa hai chunk liền kề
    chunk_min_chars: int = 80  # CHUNK_MIN_CHARS: chunk cuối ngắn hơn mức này sẽ được gộp vào chunk trước

    # Generation: có kiểm định bằng LLM không; ngưỡng cosine coi là câu trùng; số chunk lân cận làm ngữ cảnh;
    # có sinh thêm câu hỏi ngay khi người học hết câu trong ngân hàng không.
    validate_questions: bool = True  # VALIDATE_QUESTIONS: true = thêm một lượt gọi LLM kiểm định cho mỗi câu (chất lượng cao, tốn quota)
    # Loại câu có đáp án chứa số tự tính (không có trong tài liệu): model nhỏ hay sai phép tính. Xem rules.check_question.
    reject_unverified_numbers: bool = True
    dedup_threshold: float = 0.92  # DEDUP_THRESHOLD: cosine >= mức này giữa hai câu hỏi thì coi là trùng (thấp hơn = loại trùng gắt hơn)
    retrieval_top_k: int = 2  # RETRIEVAL_TOP_K: số chunk liên quan lấy thêm làm ngữ cảnh khi sinh câu
    generate_on_demand: bool = True  # GENERATE_ON_DEMAND: true = ngân hàng thiếu câu thì sinh ngay lúc người học cần

    # Grading: điểm tối thiểu để tính là đạt; ngưỡng so khớp gần đúng cho điền khuyết;
    # cho phép nhờ LLM chấm lại khi điền khuyết không khớp luật (đồng nghĩa).
    pass_threshold: float = 0.6  # PASS_THRESHOLD: điểm >= mức này tính là đạt (dùng cả ở mastery và tổng kết)
    fuzzy_threshold: float = 0.85  # FUZZY_THRESHOLD: độ giống chuỗi tối thiểu để chấp nhận đáp án điền khuyết gần đúng
    llm_fallback_for_fill_blank: bool = True  # LLM_FALLBACK_FOR_FILL_BLANK: false = điền khuyết chỉ chấm bằng luật, không gọi LLM

    # Adaptive learning: mastery_alpha là hệ số làm mượt EMA (càng lớn càng nhạy với kết quả mới nhất).
    mastery_alpha: float = 0.4  # MASTERY_ALPHA: 0..1; càng lớn thì mức nắm vững càng phụ thuộc vào lần trả lời gần nhất
    apply_level_mastery: float = 0.6  # APPLY_LEVEL_MASTERY: mastery >= ngưỡng này thì chuyển sang câu mức vận dụng
    # khoảng ôn lại (giờ) theo số lần đúng liên tiếp (Leitner đơn giản)
    # REVIEW_INTERVALS_HOURS: phần tử thứ k dùng khi chuỗi đúng liên tiếp = k (0 = sai thì ôn lại ngay); vượt độ dài thì dùng phần tử cuối.
    review_intervals_hours: list[float] = [0, 4, 24, 72, 168, 336]


@lru_cache  # đọc một lần cho cả tiến trình
def get_settings() -> Settings:
    """Trả về cấu hình dùng chung (tạo một lần rồi nhớ lại). Đổi .env thì phải khởi động lại server."""
    return Settings()

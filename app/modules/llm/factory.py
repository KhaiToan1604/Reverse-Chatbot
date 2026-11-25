"""Chọn nhà cung cấp LLM theo cấu hình (LLM_PROVIDER). Được container.py gọi một lần khi khởi động."""

from app.config import Settings
from app.modules.llm.base import LLMError, LLMProvider


def build_llm(s: Settings) -> LLMProvider:
    """Tạo nhà cung cấp LLM từ `Settings`.

    Thêm nhà cung cấp mới: viết lớp kế thừa LLMProvider, thêm một nhánh `if` ở đây, và thêm giá trị mới vào
    `llm_provider` (kiểu Literal) trong app/config.py. Ném LLMError nếu loại không được hỗ trợ.
    """
    # Import nằm trong từng nhánh để chỉ nạp mã của nhà cung cấp đang dùng.
    if s.llm_provider == "mock":
        from app.modules.llm.mock import MockLLM

        return MockLLM()
    if s.llm_provider == "gemini":
        from app.modules.llm.http_providers import GeminiProvider

        return GeminiProvider(s.llm_api_key, s.llm_model, s.llm_timeout_s, s.llm_max_retries, s.llm_base_url, s.llm_min_interval_s)
    if s.llm_provider == "openai_compat":
        from app.modules.llm.http_providers import OpenAICompatProvider

        return OpenAICompatProvider(s.llm_base_url, s.llm_model, s.llm_api_key, s.llm_timeout_s, s.llm_max_retries, s.llm_min_interval_s)
    raise LLMError(f"LLM provider không hỗ trợ: {s.llm_provider}")

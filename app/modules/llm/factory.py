from app.config import Settings
from app.modules.llm.base import LLMError, LLMProvider


def build_llm(s: Settings) -> LLMProvider:
    if s.llm_provider == "mock":
        from app.modules.llm.mock import MockLLM

        return MockLLM()
    if s.llm_provider == "gemini":
        from app.modules.llm.http_providers import GeminiProvider

        return GeminiProvider(s.llm_api_key, s.llm_model, s.llm_timeout_s, s.llm_max_retries, s.llm_base_url)
    if s.llm_provider == "openai_compat":
        from app.modules.llm.http_providers import OpenAICompatProvider

        return OpenAICompatProvider(s.llm_base_url, s.llm_model, s.llm_api_key, s.llm_timeout_s, s.llm_max_retries)
    raise LLMError(f"LLM provider không hỗ trợ: {s.llm_provider}")

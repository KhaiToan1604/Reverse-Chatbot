import pytest

from app.config import Settings
from app.modules.embedding.factory import build_embedder
from app.modules.grading.service import GradingService
from app.modules.llm.base import LLMError
from app.modules.llm.factory import build_llm
from app.modules.llm.http_providers import GeminiProvider, OpenAICompatProvider


def S(**kw):
    return Settings(_env_file=None, **kw)


def test_factories():
    assert build_llm(S(llm_provider="mock")).name
    assert build_embedder(S(embedding_provider="hashing")).name == "hashing"
    with pytest.raises(LLMError):
        build_llm(Settings.model_construct(llm_provider="nope"))
    assert isinstance(build_llm(S(llm_provider="openai_compat", llm_base_url="http://x/v1", llm_model="m")), OpenAICompatProvider)
    assert isinstance(build_llm(S(llm_provider="gemini", llm_api_key="k", llm_model="m")), GeminiProvider)


def test_provider_requires_config():
    with pytest.raises(LLMError):
        OpenAICompatProvider("", "")
    with pytest.raises(LLMError):
        GeminiProvider("", "")


class _Q:
    def __init__(self, qtype, answer="b", options=None):
        self.qtype, self.answer, self.options = qtype, answer, options
        self.question, self.rubric = "?", None


def test_empty_answer_scores_zero():
    from app.modules.llm.mock import MockLLM

    g = GradingService(S(), MockLLM())
    r = g.grade(_Q("short_answer", "x"), "   ")
    assert r.score == 0
    assert not r.is_correct

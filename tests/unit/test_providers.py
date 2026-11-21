import json

import httpx
import pytest

from app.modules.llm.base import LLMError, LLMRateLimited
from app.modules.llm.http_providers import GeminiProvider, OpenAICompatProvider


def test_openai_compat_request_and_parse():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]})

    p = OpenAICompatProvider("http://x/v1", "m", "key")
    p.client = httpx.Client(transport=httpx.MockTransport(handler))
    assert p.complete_json("sys", "usr") == {"ok": True}
    assert seen["url"] == "http://x/v1/chat/completions"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"][0]["role"] == "system"


def test_gemini_request_and_parse():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}]})

    p = GeminiProvider("k", "gemini-x")
    p.client = httpx.Client(transport=httpx.MockTransport(handler))
    assert p.complete_json("sys", "usr") == {"a": 1}
    assert seen["url"].endswith("/models/gemini-x:generateContent")
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


def _provider(handler, **kw):
    p = OpenAICompatProvider("http://x/v1", "m", "key", **kw)
    p.client = httpx.Client(transport=httpx.MockTransport(handler))
    return p


def test_retry_after_header_is_honoured(monkeypatch):
    sleeps, calls = [], []
    monkeypatch.setattr("app.modules.llm.http_providers.time.sleep", sleeps.append)

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "7"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    assert _provider(handler).complete_json("s", "u") == {}
    assert sleeps == [7.0]


def test_persistent_429_raises_rate_limited(monkeypatch):
    monkeypatch.setattr("app.modules.llm.http_providers.time.sleep", lambda _: None)
    p = _provider(lambda req: httpx.Response(429), retries=2)
    with pytest.raises(LLMRateLimited):
        p.complete_json("s", "u")


def test_persistent_503_is_plain_llm_error(monkeypatch):
    monkeypatch.setattr("app.modules.llm.http_providers.time.sleep", lambda _: None)
    p = _provider(lambda req: httpx.Response(503), retries=1)
    with pytest.raises(LLMError) as ei:
        p.complete_json("s", "u")
    assert not isinstance(ei.value, LLMRateLimited)


def test_client_error_is_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr("app.modules.llm.http_providers.time.sleep", lambda _: None)
    p = _provider(lambda req: (calls.append(1), httpx.Response(400))[1], retries=3)
    with pytest.raises(LLMError):
        p.complete_json("s", "u")
    assert len(calls) == 1


def test_throttle_spaces_calls(monkeypatch):
    sleeps = []
    clock = [100.0]
    monkeypatch.setattr("app.modules.llm.http_providers.time.sleep", lambda s: (sleeps.append(s), clock.__setitem__(0, clock[0] + s)))
    monkeypatch.setattr("app.modules.llm.http_providers.time.monotonic", lambda: clock[0])
    p = _provider(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}), min_interval=6.0)
    p.complete_json("s", "u")
    p.complete_json("s", "u")
    assert sleeps and abs(sleeps[0] - 6.0) < 1e-6

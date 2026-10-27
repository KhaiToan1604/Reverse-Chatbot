import json

import httpx

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
    assert seen["body"]["response_format"] == {"type": "json_object"} and seen["body"]["messages"][0]["role"] == "system"


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

"""Hai provider HTTP phủ gần như mọi lựa chọn miễn phí/rẻ:

- OpenAICompatProvider: Groq, Ollama (local), OpenRouter, vLLM, OpenAI... (chuẩn /chat/completions)
- GeminiProvider: Google Gemini API (free tier)
"""

import time

import httpx

from app.modules.llm.base import LLMError, LLMProvider


def _post_with_retry(client: httpx.Client, url: str, *, retries: int, **kwargs) -> httpx.Response:
    delay = 2.0
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.post(url, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as e:
            last = e
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
    raise LLMError(f"Gọi LLM thất bại: {last}")


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 60.0, retries: int = 3):
        if not base_url or not model:
            raise LLMError("openai_compat cần LLM_BASE_URL và LLM_MODEL")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.retries = retries
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.Client(timeout=timeout, headers=headers)

    def complete(self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0.3) -> str:
        payload: dict = {
            "model": self.model,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = _post_with_retry(self.client, f"{self.base_url}/chat/completions", retries=self.retries, json=payload)
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"Phản hồi LLM không đúng định dạng: {e}") from e


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0, retries: int = 3, base_url: str = ""):
        if not api_key or not model:
            raise LLMError("gemini cần LLM_API_KEY và LLM_MODEL")
        self.model = model
        self.retries = retries
        self.base_url = (base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        self.client = httpx.Client(timeout=timeout, headers={"x-goog-api-key": api_key})

    def complete(self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0.3) -> str:
        gen_cfg: dict = {"temperature": temperature}
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen_cfg,
        }
        resp = _post_with_retry(
            self.client, f"{self.base_url}/models/{self.model}:generateContent", retries=self.retries, json=payload
        )
        try:
            return "".join(p.get("text", "") for p in resp.json()["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"Phản hồi Gemini không đúng định dạng: {e}") from e

"""Hai provider HTTP phủ gần như mọi lựa chọn miễn phí/rẻ:

- OpenAICompatProvider: Groq, Ollama (local), OpenRouter, vLLM, OpenAI... (chuẩn /chat/completions)
- GeminiProvider: Google Gemini API (free tier)
"""

import time

import httpx

from app.modules.llm.base import LLMError, LLMProvider, LLMRateLimited


class _Throttle:
    """Giữ khoảng cách tối thiểu giữa hai lần gọi (chống vượt giới hạn số lần/phút của gói miễn phí)."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval > 0:
            gap = self._last + self.min_interval - time.monotonic()
            if gap > 0:
                time.sleep(gap)
        self._last = time.monotonic()


def _retry_after(resp: httpx.Response, default: float) -> float:
    """Thời gian chờ do máy chủ yêu cầu (header Retry-After, giây); không có thì dùng `default`. Tối đa 60s."""
    try:
        return min(max(float(resp.headers.get("retry-after", "")), default), 60.0)
    except ValueError:
        return default


def _post_with_retry(client: httpx.Client, url: str, *, retries: int, throttle: _Throttle | None = None, **kwargs) -> httpx.Response:
    """POST có thử lại với lỗi mạng và mã tạm thời 429/5xx (chờ 2s, 4s, 8s... hoặc theo Retry-After); 4xx khác thất bại ngay.

    Hết lượt thử mà vẫn 429 thì ném LLMRateLimited để phía trên biết dừng thay vì gọi tiếp.
    """
    delay = 2.0
    last: Exception | None = None
    limited = False
    for attempt in range(retries + 1):
        if throttle:
            throttle.wait()
        try:
            resp = client.post(url, **kwargs)
            limited = resp.status_code == 429
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(_retry_after(resp, delay))
                delay *= 2
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as e:
            last = e
            if isinstance(e, httpx.HTTPStatusError):
                break  # mã lỗi không tạm thời (400, 401, 404...) hoặc đã hết lượt thử: thử lại cũng vô ích
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
    exc = LLMRateLimited if limited else LLMError
    raise exc(f"Gọi LLM thất bại: {last}")


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(
        self, base_url: str, model: str, api_key: str = "", timeout: float = 60.0, retries: int = 3, min_interval: float = 0.0
    ):
        if not base_url or not model:
            raise LLMError("openai_compat cần LLM_BASE_URL và LLM_MODEL")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.retries = retries
        self.throttle = _Throttle(min_interval)
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
        resp = _post_with_retry(
            self.client, f"{self.base_url}/chat/completions", retries=self.retries, throttle=self.throttle, json=payload
        )
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"Phản hồi LLM không đúng định dạng: {e}") from e


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self, api_key: str, model: str, timeout: float = 60.0, retries: int = 3, base_url: str = "", min_interval: float = 0.0
    ):
        if not api_key or not model:
            raise LLMError("gemini cần LLM_API_KEY và LLM_MODEL")
        self.model = model
        self.retries = retries
        self.throttle = _Throttle(min_interval)
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
            self.client, f"{self.base_url}/models/{self.model}:generateContent", retries=self.retries, throttle=self.throttle, json=payload
        )
        try:
            return "".join(p.get("text", "") for p in resp.json()["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"Phản hồi Gemini không đúng định dạng: {e}") from e

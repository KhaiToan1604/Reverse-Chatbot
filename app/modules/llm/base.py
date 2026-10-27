import json
import re
from abc import ABC, abstractmethod
from typing import Any


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> Any:
    """Lấy JSON từ output của LLM (chịu được ```json fences và văn bản thừa)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # tìm khối {...} hoặc [...] cân bằng đầu tiên
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    raise LLMError(f"Không parse được JSON từ output: {text[:200]!r}")


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def complete(self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0.3) -> str:
        """Gọi LLM, trả về text thô."""

    def complete_json(self, system: str, user: str, *, temperature: float = 0.3, retries: int = 1) -> Any:
        """Gọi LLM và parse JSON; thử lại nếu output không hợp lệ."""
        last: Exception | None = None
        for _ in range(retries + 1):
            raw = self.complete(system, user, json_mode=True, temperature=temperature)
            try:
                return extract_json(raw)
            except LLMError as e:
                last = e
        raise LLMError(str(last))

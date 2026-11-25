"""Giao diện chung của mọi nhà cung cấp LLM và bộ trích JSON chịu lỗi.

Các module khác (generation, grading) chỉ làm việc với `LLMProvider`, không biết nhà cung cấp cụ thể là ai.
Nhờ vậy đổi Gemini/Groq/Ollama/mock chỉ cần đổi cấu hình (LLM_PROVIDER trong .env), không sửa mã.
"""

import json
import re
from abc import ABC, abstractmethod
from typing import Any


class LLMError(RuntimeError):
    """Mọi lỗi khi gọi/đọc kết quả LLM; main.py đổi thành HTTP 502, bộ chấm đổi thành chấm dự phòng."""


def extract_json(text: str) -> Any:
    """Lấy JSON từ output của LLM (chịu được ```json fences và văn bản thừa).

    Thứ tự thử: (1) bỏ rào ```json ... ``` rồi parse cả chuỗi; (2) nếu lỗi, quét tìm khối {...} hoặc [...] cân bằng đầu tiên
    parse được. Trả về dict/list; ném LLMError nếu không tìm thấy JSON hợp lệ.
    """
    text = text.strip()
    # Bỏ dòng mở ```json (hoặc ```) ở đầu và dòng ``` ở cuối, mô hình hay tự thêm dù đã yêu cầu chỉ trả JSON.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # tìm khối {...} hoặc [...] cân bằng đầu tiên
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            # Duyệt từng ký tự, đếm độ sâu ngoặc. in_str/esc để bỏ qua ngoặc nằm trong chuỗi "..." (kể cả dấu \" thoát).
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
                            break  # khối này cân bằng nhưng không phải JSON: thử ký tự mở tiếp theo
            start = text.find(opener, start + 1)
    raise LLMError(f"Không parse được JSON từ output: {text[:200]!r}")


class LLMRateLimited(LLMError):
    """Hết hạn mức gọi (HTTP 429) sau khi đã chờ và thử lại. Chạy tiếp ngay chỉ tốn thời gian: nên dừng và đợi."""


class LLMProvider(ABC):
    """Thêm nhà cung cấp mới: kế thừa lớp này, cài `complete`, rồi đăng ký trong llm/factory.py.

    Thuộc tính `name` và `model` được ghi vào bảng questions (cột model) để biết câu hỏi do mô hình nào sinh.
    """

    name: str = "base"
    model: str = ""

    @abstractmethod
    def complete(self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0.3) -> str:
        """Gọi LLM, trả về text thô.

        system: chỉ dẫn vai trò/quy tắc; user: dữ liệu của lượt này; json_mode: yêu cầu nhà cung cấp trả JSON nếu hỗ trợ;
        temperature: 0 cho việc cần ổn định (chấm, kiểm định), cao hơn cho sinh câu hỏi.
        Ném LLMError (hoặc LLMRateLimited khi hết hạn mức) nếu gọi thất bại.
        """

    def complete_json(self, system: str, user: str, *, temperature: float = 0.3, retries: int = 1) -> Any:
        """Gọi LLM và parse JSON; thử lại nếu output không hợp lệ.

        Tổng số lần gọi tối đa là retries + 1. Lỗi gọi mạng/hết hạn mức (từ `complete`) được ném lên ngay, không thử lại ở đây
        (việc thử lại với lỗi mạng đã nằm trong http_providers). Ném LLMError nếu mọi lần đều không parse được JSON.
        """
        last: Exception | None = None
        for _ in range(retries + 1):
            raw = self.complete(system, user, json_mode=True, temperature=temperature)
            try:
                return extract_json(raw)
            except LLMError as e:
                last = e
        raise LLMError(str(last))

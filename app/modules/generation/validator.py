"""LLM kiểm định lần hai: bắt các lỗi mà luật không phát hiện được (đáp án sai, mơ hồ, ngoài tài liệu).

Kiểm định theo LÔ: cả lô câu hỏi của một lượt sinh được gửi trong MỘT lần gọi LLM (trước đây mỗi câu một lần,
chiếm khoảng 2/3 tổng số lượt gọi và là nguyên nhân chính làm cạn hạn mức miễn phí).
"""

import json
import logging

from app.modules.generation.prompts import build_validate_prompt
from app.modules.llm.base import LLMError, LLMProvider, LLMRateLimited

log = logging.getLogger(__name__)


def _payload(q: dict) -> dict:
    """Phần của câu hỏi gửi cho LLM kiểm định (không gửi source_quote/giải thích để LLM tự giải độc lập)."""
    return {
        "qtype": q["qtype"],
        "question": q["question"],
        "options": q.get("options"),
        "reference_answer": q["answer"],
        "rubric": q.get("rubric"),
    }


# Ba tiêu chí LLM kiểm định phải cùng true (tên khoá trùng với SYSTEM_VALIDATE trong prompts.py; đổi thì đổi cả hai).
_KEYS = ("answerable", "answer_correct", "unambiguous")


def _as_items(res, n: int) -> dict[int, dict] | None:
    """Chuẩn hoá phản hồi của LLM về {chỉ số câu: kết quả}; None nếu không đọc được.

    Mô hình nhỏ hay lệch khỏi mẫu `{"results":[{"index":0,...}]}`, nên chấp nhận thêm:
    danh sách trần, `results` là dict, dict khoá "0","1",..., một dict kết quả đơn (lô 1 câu),
    và danh sách thiếu `index` nhưng đủ n phần tử (khi đó lấy theo thứ tự).
    """
    if isinstance(res, dict) and "results" in res:
        res = res["results"]
    if isinstance(res, dict):
        if any(k in res for k in _KEYS):  # một kết quả đơn, không bọc trong danh sách
            return {0: res} if n == 1 else None
        if res and all(str(k).strip().isdigit() and isinstance(v, dict) for k, v in res.items()):
            return {int(str(k).strip()): v for k, v in res.items()}
        return None
    if not isinstance(res, list):
        return None
    items = [r for r in res if isinstance(r, dict)]
    if not items:
        return None
    out: dict[int, dict] = {}
    for pos, r in enumerate(items):
        idx = r.get("index")
        if isinstance(idx, str) and idx.strip().isdigit():
            idx = int(idx.strip())
        if not isinstance(idx, int) or isinstance(idx, bool):
            if len(items) != n:
                return None  # không có index và không khớp số lượng -> không đoán bừa
            idx = pos
        out[idx] = r
    return out


def llm_validate_batch(llm: LLMProvider, context: str, qs: list[dict], _split: bool = True) -> list[tuple[bool, str]]:
    """Trả về [(đạt?, lý do)] theo đúng thứ tự `qs`; thường một lần gọi LLM cho cả lô.

    Nếu phản hồi của lô không đọc được và lô có >1 câu, thẩm định lại TỪNG câu (tốn thêm lượt gọi nhưng
    không loại oan cả lô vì lỗi định dạng). Lý do loại luôn kèm đoạn đầu phản hồi để chẩn đoán.
    """
    if not qs:
        return []
    # Phân biệt ba kiểu lỗi: hết hạn mức (ném lên để dừng chạy), lỗi LLM thường (loại cả lô, an toàn), sai định dạng (thử từng câu).
    system, user = build_validate_prompt(context, [_payload(q) for q in qs])
    try:
        res = llm.complete_json(system, user, temperature=0.0)
    except LLMRateLimited:
        raise  # hết hạn mức: không được coi là "câu hỏi tồi" mà phải dừng để chạy lại sau
    except LLMError as e:
        return [(False, f"validator lỗi: {e}")] * len(qs)
    by_index = _as_items(res, len(qs))
    if by_index is None:
        snippet = json.dumps(res, ensure_ascii=False)[:120]
        log.warning("validator trả về sai định dạng (lô %d câu): %s", len(qs), snippet)
        if _split and len(qs) > 1:
            return [llm_validate_batch(llm, context, [q], _split=False)[0] for q in qs]
        return [(False, f"validator trả về sai định dạng: {snippet}")] * len(qs)
    out: list[tuple[bool, str]] = []
    for i in range(len(qs)):
        r = by_index.get(i)
        if r is None:  # câu bị bỏ sót trong phản hồi -> loại (an toàn), không mặc định cho qua
            out.append((False, "validator không trả kết quả cho câu này"))
            continue
        # Cả ba tiêu chí phải đạt; thiếu/sai khoá thì bool(None) = False nên mặc định là loại (an toàn).
        ok = all(r.get(k) is True or str(r.get(k)).strip().lower() == "true" for k in _KEYS)
        # Ghi kèm giá trị từng tiêu chí SAU dấu ":" (báo cáo gom lý do theo phần trước ":") để xem validator loại vì tiêu chí nào,
        # và phát hiện được trường hợp lời giải thích ủng hộ câu hỏi nhưng cờ vẫn false (loại oan do model nhỏ).
        flags = ", ".join(f"{k}={r.get(k)}" for k in _KEYS)
        out.append((ok, "" if ok else f"validator loại: [{flags}] {str(r.get('reason', ''))[:200]}"))
    return out


def llm_validate(llm: LLMProvider, context: str, q: dict) -> tuple[bool, str]:
    """Kiểm định một câu (tiện dụng); thực chất gọi bản theo lô với lô một câu."""
    return llm_validate_batch(llm, context, [q])[0]

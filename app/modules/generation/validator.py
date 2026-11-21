"""LLM kiểm định lần hai: bắt các lỗi mà luật không phát hiện được (đáp án sai, mơ hồ, ngoài tài liệu)."""

from app.modules.generation.prompts import build_validate_prompt
from app.modules.llm.base import LLMError, LLMProvider, LLMRateLimited


def llm_validate(llm: LLMProvider, context: str, q: dict) -> tuple[bool, str]:
    """LLM kiểm định lần hai: câu hỏi có trả lời được từ tài liệu, đáp án đúng, không mơ hồ."""
    payload = {
        "qtype": q["qtype"],
        "question": q["question"],
        "options": q.get("options"),
        "reference_answer": q["answer"],
        "rubric": q.get("rubric"),
    }
    system, user = build_validate_prompt(context, payload)
    try:
        res = llm.complete_json(system, user, temperature=0.0)
    except LLMRateLimited:
        raise  # hết hạn mức: không được coi là "câu hỏi tồi" mà phải dừng để chạy lại sau
    except LLMError as e:
        return False, f"validator lỗi: {e}"
    if not isinstance(res, dict):
        return False, "validator trả về sai định dạng"
    # Cả ba tiêu chí phải đạt; thiếu/sai khoá thì bool(None) = False nên mặc định là loại (an toàn).
    ok = bool(res.get("answerable")) and bool(res.get("answer_correct")) and bool(res.get("unambiguous"))
    return ok, "" if ok else f"validator loại: {str(res.get('reason', ''))[:200]}"

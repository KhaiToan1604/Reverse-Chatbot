from app.modules.generation.prompts import build_validate_prompt
from app.modules.llm.base import LLMError, LLMProvider


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
    except LLMError as e:
        return False, f"validator lỗi: {e}"
    if not isinstance(res, dict):
        return False, "validator trả về sai định dạng"
    ok = bool(res.get("answerable")) and bool(res.get("answer_correct")) and bool(res.get("unambiguous"))
    return ok, "" if ok else f"validator loại: {str(res.get('reason', ''))[:200]}"

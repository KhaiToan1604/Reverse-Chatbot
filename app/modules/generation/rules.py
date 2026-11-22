"""Kiểm tra bằng luật (rẻ, không tốn LLM) + chuẩn hoá câu hỏi trước khi lưu."""

import random
import re

from app.common.text import norm_text
from app.modules.generation.schemas import LEVELS, QTYPES, RawQuestion

# Chỗ trống hợp lệ trong câu điền khuyết: ___ (>=3 gạch dưới), .... hoặc ……
BLANK_RE = re.compile(r"_{3,}|\.{4,}|…{2,}")
# Tiền tố "A.", "b)", "1." mà LLM hay tự thêm vào lựa chọn; cần bỏ đi trước khi lưu.
OPTION_PREFIX_RE = re.compile(r"^\s*(?:[A-Da-d][\.\):]|\d[\.\)])\s+")


def grounded(quote: str, context: str, min_tokens: int = 4) -> bool:
    """source_quote phải thực sự nằm trong context (chống LLM bịa căn cứ)."""
    q, c = norm_text(quote), norm_text(context)
    if len(q.split()) < min_tokens:
        return False
    if q in c:  # khớp nguyên văn (sau chuẩn hoá)
        return True
    # cho phép lệch nhẹ (LLM đổi vài từ): >= 92% từ của trích dẫn phải có trong ngữ cảnh
    qt = q.split()
    cset = set(c.split())
    return sum(t in cset for t in qt) / len(qt) >= 0.92


NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    """Các số trong văn bản, bỏ dấu phân cách hàng nghìn ("2.000" và "2000" coi như nhau)."""
    return {re.sub(r"[.,]", "", m) for m in NUM_RE.findall(text)}


def unverified_numbers(answer: str, context: str, question: str) -> set[str]:
    """Số có trong đáp án nhưng không có trong tài liệu lẫn câu hỏi => nhiều khả năng là kết quả tự tính của LLM."""
    return _numbers(answer) - _numbers(context) - _numbers(question)


def check_question(q: RawQuestion, context: str, reject_unverified_numbers: bool = True) -> str | None:
    """Trả về lý do loại, hoặc None nếu đạt.

    reject_unverified_numbers: loại câu có đáp án chứa số do LLM tự tính (không xuất hiện trong tài liệu hay câu hỏi). Model nhỏ
    hay sai phép tính (ví dụ quên nhân số cuốn sách) và LLM kiểm định cùng model không bắt được; thà bỏ câu còn hơn để đáp án sai
    đến tay người học. Tắt bằng REJECT_UNVERIFIED_NUMBERS=false khi đã dùng model mạnh hoặc có người duyệt.
    """
    if q.qtype not in QTYPES:
        return f"qtype không hợp lệ: {q.qtype}"
    if q.level not in LEVELS:
        return f"level không hợp lệ: {q.level}"
    if not (10 <= len(q.question.strip()) <= 1200):
        return "độ dài câu hỏi bất thường"
    if not grounded(q.source_quote, context):
        return "source_quote không có trong tài liệu (không có căn cứ)"

    if q.qtype == "mcq":
        opts = [OPTION_PREFIX_RE.sub("", o).strip() for o in (q.options or [])]
        if len(opts) != 4 or any(not o for o in opts):
            return "mcq cần đúng 4 lựa chọn không rỗng"
        if len({norm_text(o) for o in opts}) != 4:
            return "mcq có lựa chọn trùng nhau"
        if q.correct_index is None or not 0 <= q.correct_index < 4:
            return "mcq thiếu correct_index hợp lệ"
    elif q.qtype == "fill_blank":
        if len(BLANK_RE.findall(q.question)) != 1:
            return "fill_blank cần đúng một chỗ trống ____"
        if not q.answer.strip() or len(q.answer.split()) > 6:
            return "đáp án fill_blank rỗng hoặc quá dài"
        if norm_text(q.answer) not in norm_text(context):
            return "đáp án fill_blank không xuất hiện trong tài liệu"
    else:  # short_answer | scenario
        if not q.answer.strip():
            return "thiếu đáp án chuẩn"
        if not q.rubric or len(q.rubric) < 2:
            return "tự luận cần rubric ít nhất 2 ý"
        if any(not r.point.strip() for r in q.rubric):
            return "rubric có ý rỗng"

    if reject_unverified_numbers:
        # mcq: chỉ xét lựa chọn đúng (các lựa chọn nhiễu được phép có số bất kỳ).
        answer = OPTION_PREFIX_RE.sub("", q.options[q.correct_index]).strip() if q.qtype == "mcq" and q.options else q.answer  # type: ignore[index]
        extra = unverified_numbers(answer, context, q.question)
        if extra:
            return f"đáp án chứa số không có trong tài liệu ({', '.join(sorted(extra))}): có thể là kết quả tính toán chưa kiểm chứng"
    return None


def finalize(q: RawQuestion) -> dict:
    """Chuẩn hoá thành dict lưu DB. MCQ: xáo lựa chọn bằng code để tránh LLM thiên vị vị trí đáp án."""
    out: dict = {
        "qtype": q.qtype,
        "level": q.level,
        "question": q.question.strip(),
        "explanation": q.explanation.strip(),
        "source_quote": q.source_quote.strip(),
        "options": None,
        "rubric": None,
        "meta": {},
    }
    if q.qtype == "mcq":
        opts = [OPTION_PREFIX_RE.sub("", o).strip() for o in (q.options or [])]
        correct_text = opts[q.correct_index]  # type: ignore[index]
        rng = random.Random(norm_text(q.question))  # xáo tất định theo nội dung câu hỏi
        rng.shuffle(opts)
        out["options"] = opts
        out["answer"] = "ABCD"[opts.index(correct_text)]
    else:
        out["answer"] = q.answer.strip()
    if q.qtype == "fill_blank":
        out["meta"]["alt_answers"] = [a.strip() for a in q.alt_answers if a.strip()]
    if q.qtype in ("short_answer", "scenario") and q.rubric:
        total = sum(max(r.weight, 0) for r in q.rubric) or float(len(q.rubric))
        out["rubric"] = [
            {"point": r.point.strip(), "weight": round((max(r.weight, 0) or 1.0) / total, 4)} for r in q.rubric
        ]
        s = sum(r["weight"] for r in out["rubric"])
        # làm tròn có thể lệch vài phần vạn: bù vào ý cuối để tổng trọng số đúng bằng 1
        out["rubric"][-1]["weight"] = round(out["rubric"][-1]["weight"] + (1 - s), 4)  # tổng đúng 1
    return out

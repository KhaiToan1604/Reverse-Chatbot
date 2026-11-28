"""Kiểm tra bằng luật (rẻ, không tốn LLM) + chuẩn hoá câu hỏi trước khi lưu.

Đây là lớp kiểm định thứ nhất trong ba lớp (luật -> LLM kiểm định ở validator.py -> loại trùng ở service.py).
Được generation/service.py gọi: ensure_rubric -> repair_fill_blank -> check_question (trả lý do loại hoặc None)
-> finalize (dict để lưu DB).
Ngưỡng và số lượng cố định (4 lựa chọn, tối đa 6 từ cho điền khuyết, 92% trích dẫn...) nằm ngay trong các hàm dưới; sửa tại đây.
"""

import ast
import random
import re
from fractions import Fraction

from app.common.text import norm_text
from app.modules.generation.schemas import LEVELS, QTYPES, RawQuestion, RubricItem

# Chỗ trống hợp lệ trong câu điền khuyết: ___ (>=3 gạch dưới), .... hoặc ……
BLANK_RE = re.compile(r"_{3,}|\.{4,}|…{2,}")
# Tiền tố "A.", "b)", "1." mà LLM hay tự thêm vào lựa chọn; cần bỏ đi trước khi lưu.
OPTION_PREFIX_RE = re.compile(r"^\s*(?:[A-Da-d][\.\):]|\d[\.\)])\s+")


def grounded(quote: str, context: str, min_tokens: int = 4) -> bool:
    """source_quote phải thực sự nằm trong context (chống LLM bịa căn cứ).

    min_tokens: trích dẫn ngắn hơn số từ này bị coi là không đủ làm căn cứ. Ngưỡng lệch 0,92 sửa ở dòng cuối hàm.
    """
    q, c = norm_text(quote), norm_text(context)
    if len(q.split()) < min_tokens:
        return False
    if q in c:  # khớp nguyên văn (sau chuẩn hoá)
        return True
    # cho phép lệch nhẹ (LLM đổi vài từ): >= 92% từ của trích dẫn phải có trong ngữ cảnh
    qt = q.split()
    cset = set(c.split())
    return sum(t in cset for t in qt) / len(qt) >= 0.92


def ensure_rubric(q: RawQuestion) -> None:
    """short_answer mà LLM không đưa rubric: dùng chính đáp án chuẩn làm một ý duy nhất (trọng số 1).

    Câu hỏi một thông tin ("Cần kết nối qua đâu?") chỉ có một ý để chấm; ép model bịa thêm ý thứ hai làm loại oan câu đúng.
    Chỉ áp dụng cho short_answer: scenario là tình huống nhiều bước nên vẫn bắt buộc có ít nhất 2 ý.
    """
    if q.qtype == "short_answer" and not q.rubric and q.answer.strip():
        q.rubric = [RubricItem(point=q.answer.strip(), weight=1.0)]


def repair_fill_blank(q: RawQuestion) -> None:
    """fill_blank mà LLM quên chỗ trống nhưng câu hỏi lại chứa nguyên đáp án: thay đáp án bằng ____ (sửa tại chỗ).

    Ví dụ "Thư viện mở cửa lúc 8 giờ sáng." với đáp án "8" -> "Thư viện mở cửa lúc ____ giờ sáng.". Rất thận trọng để không sửa sai:
    chỉ sửa khi câu CHƯA có chỗ trống nào và đáp án (nguyên cụm, không phân biệt hoa thường) xuất hiện ĐÚNG MỘT lần trong câu hỏi.
    Không đủ điều kiện thì để nguyên và check_question sẽ loại câu như trước. Được service.py gọi ngay sau ensure_rubric.
    """
    answer = q.answer.strip()
    if q.qtype != "fill_blank" or not answer or BLANK_RE.search(q.question):
        return
    # (?<!\w)/(?!\w): đáp án "8" không được khớp bên trong "18" hay "80".
    pattern = re.compile(rf"(?<!\w){re.escape(answer)}(?!\w)", re.IGNORECASE)
    if len(pattern.findall(q.question)) == 1:
        q.question = pattern.sub("____", q.question, count=1)


NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")  # số, kể cả dạng có dấu phân cách hàng nghìn/thập phân: 2.000, 1,5


def _numbers(text: str) -> set[str]:
    """Các số trong văn bản, bỏ dấu phân cách hàng nghìn ("2.000" và "2000" coi như nhau)."""
    return {re.sub(r"[.,]", "", m) for m in NUM_RE.findall(text)}


def unverified_numbers(answer: str, context: str, question: str) -> set[str]:
    """Số có trong đáp án nhưng không có trong tài liệu lẫn câu hỏi => nhiều khả năng là kết quả tự tính của LLM."""
    return _numbers(answer) - _numbers(context) - _numbers(question)


# Giới hạn kích thước biểu thức để phép tính của LLM không thể gây tốn tài nguyên (độ dài chuỗi, số nút cú pháp).
_MAX_CALC_LEN = 100
_MAX_CALC_NODES = 40


def eval_calculation(expr: str) -> tuple[int, set[str]] | None:
    """Tính lại biểu thức số học của LLM một cách an toàn. Trả về (kết quả nguyên, tập các toán hạng) hoặc None nếu không hợp lệ.

    Chỉ cho phép số nguyên, + - * / và ngoặc (không luỹ thừa, không tên hàm, không biến) nên không thể thực thi mã tuỳ ý.
    Tính bằng Fraction để phép chia chính xác; kết quả phải là số nguyên dương.
    """
    text = expr.split("=")[0].replace("×", "*").replace("÷", "/").replace(" ", "")
    if not text or len(text) > _MAX_CALC_LEN:
        return None
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return None
    if sum(1 for _ in ast.walk(tree)) > _MAX_CALC_NODES:
        return None
    operands: set[str] = set()

    def ev(node: ast.AST) -> Fraction:
        """Duyệt cây cú pháp, chỉ chấp nhận số nguyên và + - * / ; mọi loại nút khác bị từ chối (ValueError)."""
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and type(node.value) is int:
            operands.add(str(node.value))
            return Fraction(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if b == 0:
                raise ZeroDivisionError
            return a / b
        raise ValueError("biểu thức không được phép")

    try:
        value = ev(tree)
    except (ValueError, ZeroDivisionError, RecursionError):
        return None
    if value.denominator != 1 or value <= 0:
        return None
    return int(value), operands


def calculation_supports(calc: str | None, extra: set[str], context: str, question: str) -> bool:
    """Đáp án chứa số tự tính `extra` được chấp nhận khi biểu thức của LLM, do code tính lại, chứng minh đúng số đó.

    Điều kiện: (1) kết quả đúng bằng số duy nhất chưa kiểm chứng trong đáp án; (2) mọi toán hạng đều lấy từ tài liệu hoặc câu hỏi;
    (3) mọi con số nêu trong câu hỏi đều được dùng làm toán hạng. Điều kiện (3) chặn lỗi hay gặp của model nhỏ là quên một đại lượng
    (ví dụ chỉ tính 10 ngày x 2.000 mà bỏ số cuốn sách nêu trong câu hỏi): câu như vậy bị loại thay vì cho đáp án sai qua.
    """
    res = eval_calculation(calc) if calc else None
    if res is None:
        return False
    value, operands = res
    allowed = _numbers(context) | _numbers(question)
    return extra == {str(value)} and operands <= allowed and _numbers(question) <= operands


def check_question(q: RawQuestion, context: str, reject_unverified_numbers: bool = True) -> str | None:
    """Trả về lý do loại, hoặc None nếu đạt.

    q: câu thô do LLM sinh; context: văn bản mà câu phải có căn cứ trong đó.
    Các kiểm tra theo thứ tự: loại/mức hợp lệ -> độ dài -> source_quote có thật -> luật riêng từng loại (mcq, fill_blank, tự luận)
    -> số trong đáp án có căn cứ. Lý do trả về được lưu vào cột reject_reason và hiện ở báo cáo đánh giá.

    reject_unverified_numbers: loại câu có đáp án chứa số do LLM tự tính (không xuất hiện trong tài liệu hay câu hỏi). Model nhỏ
    hay sai phép tính (ví dụ quên nhân số cuốn sách) và LLM kiểm định cùng model không bắt được; thà bỏ câu còn hơn để đáp án sai
    đến tay người học. Tắt bằng REJECT_UNVERIFIED_NUMBERS=false khi đã dùng model mạnh hoặc có người duyệt.
    """
    if q.qtype not in QTYPES:
        return f"qtype không hợp lệ: {q.qtype}"
    if q.level not in LEVELS:
        return f"level không hợp lệ: {q.level}"
    if not (10 <= len(q.question.strip()) <= 1200):  # giới hạn độ dài câu hỏi (ký tự)
        return "độ dài câu hỏi bất thường"
    if not grounded(q.source_quote, context):
        return "source_quote không có trong tài liệu (không có căn cứ)"

    if q.qtype == "mcq":
        opts = [OPTION_PREFIX_RE.sub("", o).strip() for o in (q.options or [])]
        if len(opts) != 4 or any(not o for o in opts):
            # Số lựa chọn cố định là 4 (A..D); đổi thì sửa cả finalize() và grading/rule_based.py.
            return "mcq cần đúng 4 lựa chọn không rỗng"
        if len({norm_text(o) for o in opts}) != 4:
            return "mcq có lựa chọn trùng nhau"
        if q.correct_index is None or not 0 <= q.correct_index < 4:
            return "mcq thiếu correct_index hợp lệ"
    elif q.qtype == "fill_blank":
        if len(BLANK_RE.findall(q.question)) != 1:
            return "fill_blank cần đúng một chỗ trống ____"
        if not q.answer.strip() or len(q.answer.split()) > 6:  # đáp án điền khuyết tối đa 6 từ (prompt dặn tối đa 5 từ)
            return "đáp án fill_blank rỗng hoặc quá dài"
        if norm_text(q.answer) not in norm_text(context):
            return "đáp án fill_blank không xuất hiện trong tài liệu"
    else:  # short_answer | scenario
        if not q.answer.strip():
            return "thiếu đáp án chuẩn"
        min_points = 2 if q.qtype == "scenario" else 1  # scenario: tình huống nhiều bước; short_answer: có thể chỉ một ý
        if not q.rubric or len(q.rubric) < min_points:
            return f"tự luận cần rubric ít nhất {min_points} ý"
        if any(not r.point.strip() for r in q.rubric):
            return "rubric có ý rỗng"

    if reject_unverified_numbers:
        # Khối này chặn lỗi "đáp án là số tự tính sai". mcq: chỉ xét lựa chọn đúng (các lựa chọn nhiễu được phép có số bất kỳ).
        answer = OPTION_PREFIX_RE.sub("", q.options[q.correct_index]).strip() if q.qtype == "mcq" and q.options else q.answer  # type: ignore[index]
        extra = unverified_numbers(answer, context, q.question)
        computed: set[str] = set()
        if extra:
            if not calculation_supports(q.calculation, extra, context, q.question):
                hint = "; phép tính kèm theo không chứng minh được đáp án" if q.calculation else ""
                return (f"đáp án chứa số không có trong tài liệu ({', '.join(sorted(extra))}): "
                        f"có thể là kết quả tính toán chưa kiểm chứng{hint}")
            computed = extra  # số này đã được chứng minh bằng phép tính
        # Căn cứ phải nâng đỡ được đáp án: số trong đáp án phải nằm trong source_quote (hoặc câu hỏi / kết quả phép tính). Nếu không,
        # trích dẫn chỉ "có trong tài liệu" chứ không chứng minh gì (ví dụ đáp án dùng giới hạn 50 trang nhưng trích dẫn nói về VPN).
        unsupported = _numbers(answer) - _numbers(q.source_quote) - _numbers(q.question) - computed
        if unsupported:
            return (f"số trong đáp án ({', '.join(sorted(unsupported))}) không nằm trong source_quote: "
                    "trích dẫn không đủ làm căn cứ cho đáp án")
    return None


def finalize(q: RawQuestion) -> dict:
    """Chuẩn hoá thành dict lưu DB. MCQ: xáo lựa chọn bằng code để tránh LLM thiên vị vị trí đáp án.

    Chỉ gọi sau khi check_question đã đạt (nên các chỉ số và danh sách ở đây được coi là hợp lệ). Khoá của dict khớp cột của
    bảng questions (app/db/models.py); `meta` chứa thông tin phụ: calculation, alt_answers. Với mcq, `answer` là chữ cái A..D.
    """
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
        # Hạt giống lấy từ nội dung câu hỏi nên sinh lại cùng câu thì ra cùng thứ tự (tái lập được, dễ so sánh giữa các lần chạy).
        rng = random.Random(norm_text(q.question))  # xáo tất định theo nội dung câu hỏi
        rng.shuffle(opts)
        out["options"] = opts
        out["answer"] = "ABCD"[opts.index(correct_text)]
    else:
        out["answer"] = q.answer.strip()
    if q.calculation:
        out["meta"]["calculation"] = q.calculation.strip()
    if q.qtype == "fill_blank":
        out["meta"]["alt_answers"] = [a.strip() for a in q.alt_answers if a.strip()]
    if q.qtype in ("short_answer", "scenario") and q.rubric:
        # Chuẩn hoá trọng số về tổng 1; trọng số âm/0 được thay bằng 1 trước khi chia (LLM không phải lúc nào cũng cho tổng đúng 1).
        raw_w = [max(r.weight, 0) or 1.0 for r in q.rubric]  # trọng số <= 0 -> 1 (tính TRƯỚC khi lấy tổng để tổng luôn khớp)
        total = sum(raw_w)
        out["rubric"] = [{"point": r.point.strip(), "weight": round(w / total, 4)} for r, w in zip(q.rubric, raw_w, strict=True)]
        s = sum(r["weight"] for r in out["rubric"])
        # làm tròn có thể lệch vài phần vạn: bù vào ý cuối để tổng trọng số đúng bằng 1
        out["rubric"][-1]["weight"] = round(out["rubric"][-1]["weight"] + (1 - s), 4)  # tổng đúng 1
    return out

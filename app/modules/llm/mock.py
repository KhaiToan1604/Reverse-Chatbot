"""MockLLM: LLM giả tất định để dev/test offline (không cần API key, không tốn quota).

Nó đọc các khối <<<...>>> trong prompt và dựng câu hỏi/chấm điểm đơn giản từ chính văn bản.
Chất lượng không đại diện cho LLM thật — chỉ để kiểm tra luồng hệ thống.
"""

import json
import re

from app.modules.grading.heuristic import point_covered
from app.modules.llm.base import LLMProvider
from app.modules.llm.markers import get_section


def _sentences(context: str) -> list[str]:
    body = re.sub(r"^\[Mục:.*?\]\s*$", "", context, flags=re.M)
    out = []
    for line in re.split(r"\n+|(?<=[.!?])\s+", body):
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if len(line.split()) >= 6 and line != "---":
            out.append(line)
    return out


class MockLLM(LLMProvider):
    name = "mock"
    model = "mock-1"

    def complete(self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0.3) -> str:
        if "[[TASK:generate]]" in system:
            return json.dumps(self._generate(user), ensure_ascii=False)
        if "[[TASK:validate]]" in system:
            return json.dumps({"answerable": True, "answer_correct": True, "unambiguous": True, "reason": "mock"})
        if "[[TASK:grade]]" in system:
            return json.dumps(self._grade(user), ensure_ascii=False)
        return "{}"

    # -- sinh câu hỏi --
    def _generate(self, user: str) -> dict:
        context = get_section(user, "CONTEXT") or ""
        specs = json.loads(get_section(user, "SPEC") or "[]")
        sents = _sentences(context)
        qs = []
        for i, sp in enumerate(specs):
            if not sents:  # baseline không RAG: không có tài liệu -> câu hỏi không có căn cứ
                topic = re.sub(r"^\[Mục:\s*|\]$", "", context.strip())
                qs.append({"qtype": sp["qtype"], "level": sp["level"], "question": f"Hãy nêu quy định về {topic}?",
                           "options": None, "correct_index": None, "answer": "không rõ", "alt_answers": [],
                           "rubric": [{"point": "ý một", "weight": 0.5}, {"point": "ý hai", "weight": 0.5}],
                           "explanation": "", "source_quote": ""})
                continue
            s = sents[i % len(sents)]
            words = s.rstrip(".").split()
            base = {"qtype": sp["qtype"], "level": sp["level"], "options": None, "correct_index": None,
                    "alt_answers": [], "rubric": None, "explanation": f"Theo tài liệu: {s}", "source_quote": s}
            if sp["qtype"] == "fill_blank":
                idx = max(range(len(words)), key=lambda k: len(re.sub(r"\W", "", words[k])))
                ans = re.sub(r"^\W+|\W+$", "", words[idx])
                blanked = " ".join(words[:idx] + ["____"] + words[idx + 1 :])
                base.update(question=f"Điền vào chỗ trống: {blanked}", answer=ans)
            elif sp["qtype"] == "mcq":
                base.update(
                    question=f"Phát biểu nào sau đây đúng theo tài liệu về nội dung: «{' '.join(words[:5])}...»?",
                    options=[s, "Tài liệu không đề cập nội dung này.", "Quy định này chỉ áp dụng cho giảng viên.",
                             "Quy định này đã bị bãi bỏ."],
                    correct_index=0, answer=s)
            else:
                half = max(1, len(words) // 2)
                base.update(
                    question=(f"Tình huống: bạn gặp trường hợp liên quan đến «{' '.join(words[:4])}». Bạn sẽ xử lý thế nào?"
                              if sp["qtype"] == "scenario" else f"Hãy trình bày nội dung liên quan đến «{' '.join(words[:4])}»."),
                    answer=s,
                    rubric=[{"point": " ".join(words[:half]), "weight": 0.5}, {"point": " ".join(words[half:]), "weight": 0.5}])
            qs.append(base)
        return {"questions": qs}

    # -- chấm điểm --
    def _grade(self, user: str) -> dict:
        rubric = json.loads(get_section(user, "RUBRIC") or "[]")
        student = get_section(user, "STUDENT") or ""
        covered = [point_covered(r["point"], student) for r in rubric]
        return {"covered": covered, "feedback": "Chấm bởi MockLLM (theo độ phủ từ khoá)."}

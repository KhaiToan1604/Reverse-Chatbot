from app.db.base import session_scope
from app.db.models import Chunk, Question
from app.modules.llm.base import LLMError, LLMRateLimited
from app.modules.llm.mock import MockLLM


class _LimitedLLM(MockLLM):
    """Cho qua `ok_calls` lượt đầu rồi báo hết hạn mức."""

    def __init__(self, ok_calls, exc=LLMRateLimited):
        self.ok_calls, self.exc, self.n = ok_calls, exc, 0

    def complete(self, system, user, **kw):
        self.n += 1
        if self.n > self.ok_calls:
            raise self.exc("429")
        return super().complete(system, user, **kw)


def _first_chunk(db):
    return db.query(Chunk).order_by(Chunk.id).first()


def test_only_missing_skips_covered_specs_and_saves_calls(loaded):
    client, _ = loaded
    gen = client.app.state.container.generation
    with session_scope() as db:
        ch = _first_chunk(db)
        assert gen.generate_for_chunk(db, ch).created
        gen.llm = _LimitedLLM(ok_calls=0)  # mọi lượt gọi đều lỗi
        rep = gen.generate_for_chunk(db, ch, only_missing=True)  # đã đủ -> không gọi LLM nào
        assert not rep.errors and gen.llm.n == 0


def test_rate_limit_stops_early_and_keeps_partial_work(loaded):
    client, _ = loaded
    gen = client.app.state.container.generation
    with session_scope() as db:
        ch = _first_chunk(db)
        gen.llm = _LimitedLLM(ok_calls=1)  # lượt sinh "recall" ok (+ kiểm định bị chặn)
        rep = gen.generate_for_chunk(db, ch)
        assert rep.rate_limited
        assert gen.llm.n <= 3  # dừng ngay, không gọi nốt mức "apply"
        assert db.query(Question).filter(Question.status == "rejected", Question.reject_reason.like("validator lỗi%")).count() == 0


def test_plain_llm_error_does_not_set_rate_limited(loaded):
    client, _ = loaded
    gen = client.app.state.container.generation
    with session_scope() as db:
        gen.llm = _LimitedLLM(ok_calls=0, exc=LLMError)
        rep = gen.generate_for_chunk(db, _first_chunk(db))
        assert rep.errors and not rep.rate_limited


class _Scripted(MockLLM):
    """Trả đúng JSON do test quy định cho lượt sinh; lượt kiểm định luôn cho qua."""

    def __init__(self, questions):
        self.questions = questions

    def complete(self, system, user, **kw):
        import json

        if "[[TASK:validate]]" in system:
            ok = {"answerable": True, "answer_correct": True, "unambiguous": True, "working": "", "reason": ""}
            return json.dumps({"results": [{"index": i, **ok} for i in range(10)]})
        return json.dumps({"questions": self.questions})


def _quote(chunk):
    return " ".join(chunk.text.split()[:10])


def _open_q(qtype, chunk, **kw):
    base = {"qtype": qtype, "level": "apply", "question": "Câu hỏi tình huống về nội quy thư viện được hỏi như thế nào?",
            "answer": _quote(chunk), "explanation": "theo tài liệu", "source_quote": _quote(chunk)}
    return {**base, **kw}


def test_short_answer_without_rubric_is_saved_with_single_point_rubric(loaded):
    from app.modules.generation.schemas import Spec

    client, _ = loaded
    gen = client.app.state.container.generation
    with session_scope() as db:
        ch = _first_chunk(db)
        gen.llm = _Scripted([_open_q("short_answer", ch, rubric=None)])
        rep = gen.generate_for_chunk(db, ch, [Spec("short_answer", "apply")])
        assert len(rep.created) == 1 and not rep.rejected
        assert rep.created[0].rubric == [{"point": _quote(ch), "weight": 1.0}]


def test_scenario_with_one_rubric_point_is_still_rejected(loaded):
    from app.modules.generation.schemas import Spec

    client, _ = loaded
    gen = client.app.state.container.generation
    with session_scope() as db:
        ch = _first_chunk(db)
        gen.llm = _Scripted([_open_q("scenario", ch, rubric=[{"point": "một ý", "weight": 1}])])
        rep = gen.generate_for_chunk(db, ch, [Spec("scenario", "apply")])
        assert not rep.created and "ít nhất 2 ý" in rep.rejected[0].reject_reason


def test_computed_answer_is_saved_only_when_its_calculation_checks_out(loaded):
    from app.modules.generation.schemas import Spec

    client, _ = loaded
    gen = client.app.state.container.generation
    with session_scope() as db:
        ch = db.query(Chunk).filter(Chunk.text.like("%2.000 đồng%")).order_by(Chunk.id).first()
        quote = "Sách trả trễ bị phạt 2.000 đồng cho mỗi cuốn mỗi ngày quá hạn."
        q = "Sinh viên A mượn 3 cuốn sách giáo trình và trả muộn 10 ngày. Sinh viên A phải trả bao nhiêu tiền phạt?"
        good = _open_q("short_answer", ch, question=q, source_quote=quote, answer="60.000 đồng", calculation="3*10*2000", rubric=None)
        bad = _open_q("short_answer", ch, question=q + " (bản 2)", source_quote=quote, answer="20.000 đồng",
                      calculation="10*2000", rubric=None)
        gen.llm = _Scripted([good, bad])
        rep = gen.generate_for_chunk(db, ch, [Spec("short_answer", "apply", 2)])
        assert [x.answer for x in rep.created] == ["60.000 đồng"]
        assert rep.created[0].meta["calculation"] == "3*10*2000"
        assert len(rep.rejected) == 1 and "phép tính kèm theo" in rep.rejected[0].reject_reason

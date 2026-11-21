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

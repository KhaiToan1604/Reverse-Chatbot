"""Chọn câu hỏi kế tiếp cho người học (được modules/quiz/service.py gọi mỗi lần cần câu mới).

Hai quyết định: (1) học mục (chunk) nào: chưa học trước, rồi mục đến hạn ôn, rồi các mục còn lại; (2) hỏi mức nào:
nhớ hay vận dụng, theo mức nắm vững. Muốn đổi chiến lược chọn: sửa hàm `priority` trong `QuestionSelector.pick`.
"""

import logging
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Attempt, Chunk, Mastery, Question, QuizSession, utcnow
from app.modules.adaptive.mastery import desired_level
from app.modules.generation.schemas import Spec
from app.modules.generation.service import GenerationService

log = logging.getLogger(__name__)
MAX_ON_DEMAND_TRIES = 3  # số lần tối đa gọi LLM sinh câu bổ sung trong MỘT lượt chọn câu (tránh người học chờ quá lâu)


def specs_for_level(level: str) -> list[Spec]:
    """Loại câu hỏi cần sinh thêm cho từng mức: vận dụng = tình huống + tự luận ngắn; nhớ = trắc nghiệm + điền khuyết."""
    if level == "apply":
        return [Spec("scenario", "apply"), Spec("short_answer", "apply")]
    return [Spec("mcq", "recall"), Spec("fill_blank", "recall")]


class QuestionSelector:
    """Chọn câu tiếp theo: chunk chưa học -> chunk đến hạn ôn (yếu trước) -> chunk còn lại.
    Mức câu hỏi (nhớ / vận dụng) theo mastery. Thiếu câu trong ngân hàng thì sinh theo yêu cầu."""

    def __init__(self, settings: Settings, generator: GenerationService | None = None):
        """`generator` có thể là None: khi đó chỉ chọn từ ngân hàng câu hỏi có sẵn, không sinh thêm."""
        self.s = settings
        self.generator = generator

    def pick(self, db: Session, user_id: int, session: QuizSession, rng: random.Random | None = None) -> Question | None:
        """Trả về câu hỏi hợp lệ kế tiếp, hoặc None nếu không có tài liệu/câu hỏi phù hợp. `rng` để chọn ngẫu nhiên tái lập được."""
        rng = rng or random.Random()
        now = utcnow()
        stmt = select(Chunk).order_by(Chunk.id)
        if session.document_id:
            stmt = stmt.where(Chunk.document_id == session.document_id)
        chunks = db.scalars(stmt).all()
        if not chunks:
            return None

        mastery = {
            m.chunk_id: m
            for m in db.scalars(select(Mastery).where(Mastery.user_id == user_id, Mastery.chunk_id.in_([c.id for c in chunks])))
        }
        sess_rows = db.execute(
            select(Attempt.question_id, Question.chunk_id).join(Question).where(Attempt.session_id == session.id)
        ).all()
        asked_q = {r[0] for r in sess_rows}
        asked_chunks = {r[1] for r in sess_rows}

        # Khoá sắp xếp (nhỏ hơn = ưu tiên hơn): (đã hỏi trong phiên này, nhóm, khoá phụ)
        #   nhóm 0: chưa học (ngẫu nhiên)  | nhóm 1: đến hạn ôn (yếu trước) | nhóm 2: chưa đến hạn (sắp đến hạn trước)
        def priority(c: Chunk) -> tuple:
            m = mastery.get(c.id)
            if m is None:
                tier, key = 0, rng.random()
            elif m.due_at is None or m.due_at <= now:
                tier, key = 1, m.mastery
            else:
                tier, key = 2, (m.due_at - now).total_seconds()
            return (c.id in asked_chunks, tier, key)  # tránh lặp chunk trong cùng phiên

        # Duyệt chunk theo ưu tiên, lấy câu đầu tiên tìm được; sinh theo yêu cầu tối đa MAX_ON_DEMAND_TRIES lần để không treo.
        tries = 0
        for c in sorted(chunks, key=priority):
            level = desired_level(mastery.get(c.id), self.s)
            q = self._from_bank(db, user_id, c.id, level, asked_q)
            if q is None and self.generator and self.s.generate_on_demand and tries < MAX_ON_DEMAND_TRIES:
                tries += 1
                self.generator.generate_for_chunk(db, c, specs_for_level(level))
                q = self._from_bank(db, user_id, c.id, level, asked_q)
            if q:
                return q
        return None

    def _from_bank(self, db: Session, user_id: int, chunk_id: int, level: str, asked_q: set[int]) -> Question | None:
        """Chọn một câu hợp lệ chưa hỏi trong phiên: ưu tiên đúng mức, rồi câu người này ít được hỏi nhất."""
        qs = db.scalars(select(Question).where(Question.chunk_id == chunk_id, Question.status == "valid")).all()
        qs = [q for q in qs if q.id not in asked_q]
        if not qs:
            return None
        counts = dict(
            db.execute(
                select(Attempt.question_id, func.count())
                .where(Attempt.user_id == user_id, Attempt.question_id.in_([q.id for q in qs]))
                .group_by(Attempt.question_id)
            ).all()
        )
        qs.sort(key=lambda q: (q.level != level, counts.get(q.id, 0), q.id))  # đúng mức -> ít được hỏi nhất
        return qs[0]

from app.common.text import norm_loose, norm_text
from app.config import Settings
from app.db.models import Mastery, Question
from app.modules.adaptive.mastery import apply_attempt, desired_level
from app.modules.generation.rules import check_question, finalize, grounded
from app.modules.generation.schemas import RawQuestion
from app.modules.grading.rule_based import grade_fill_blank_rule, grade_mcq
from app.modules.ingestion.chunker import chunk_text
from app.modules.llm.base import extract_json
from app.modules.vectorstore.numpy_store import NumpyVectorStore
import numpy as np


def test_chunker_respects_headings_and_size():
    text = "# A\n\n" + ("Câu một dài dài. " * 60) + "\n\n## B\n\nNội dung ngắn nhưng đủ dài để thành một chunk riêng biệt trong test này."
    chunks = chunk_text(text, max_chars=300, overlap=40)
    assert all(len(c.text) <= 300 + 60 for c in chunks)
    assert {c.heading for c in chunks} == {"A", "A > B"}
    assert len(chunks) > 3


def test_extract_json_handles_fences_and_noise():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Đây là kết quả: {"a": [1, 2]} hết') == {"a": [1, 2]}


def test_norm_vietnamese():
    assert norm_text("  Hạn MƯỢN, 14 ngày! ") == "hạn mượn 14 ngày"
    assert norm_loose("Đặt phòng") == "dat phong"


def test_grounded_rejects_invented_quote():
    ctx = "Sinh viên được mượn tối đa 5 cuốn sách giáo trình trong một lần mượn."
    assert grounded("mượn tối đa 5 cuốn sách giáo trình", ctx)
    assert not grounded("mượn tối đa 50 cuốn tạp chí khoa học", ctx)


def _raw(**kw):
    base = dict(qtype="mcq", level="recall", question="Sinh viên mượn tối đa bao nhiêu cuốn?", options=["3", "5", "7", "10"],
                correct_index=1, answer="5", source_quote="mượn tối đa 5 cuốn sách giáo trình trong một lần")
    base.update(kw)
    return RawQuestion(**base)


CTX = "Sinh viên được mượn tối đa 5 cuốn sách giáo trình trong một lần mượn."


def test_rules_and_mcq_shuffle():
    assert check_question(_raw(), CTX) is None
    assert "4 lựa chọn" in check_question(_raw(options=["3", "5"]), CTX)
    assert "căn cứ" in check_question(_raw(source_quote="nội dung bịa đặt hoàn toàn không có"), CTX)
    fin = finalize(_raw())
    assert fin["options"]["ABCD".index(fin["answer"])] == "5"  # đáp án vẫn đúng sau khi xáo


def _q(**kw):
    base = dict(id=1, chunk_id=1, qtype="mcq", level="recall", question="q", options=["x", "y", "z", "w"], answer="C", meta={})
    base.update(kw)
    return Question(**base)


def test_grade_mcq_accepts_letter_or_text():
    q = _q()
    assert grade_mcq(q, "c").is_correct and grade_mcq(q, "C.").is_correct and grade_mcq(q, "z").is_correct
    assert not grade_mcq(q, "a").is_correct


def test_fill_blank_tolerates_accents_and_typos():
    q = _q(qtype="fill_blank", options=None, answer="14 ngày", meta={"alt_answers": ["mười bốn ngày"]})
    assert grade_fill_blank_rule(q, "14 ngay", 0.85)
    assert grade_fill_blank_rule(q, "mười bốn ngày", 0.85)
    assert grade_fill_blank_rule(q, "7 ngày", 0.85) is None


def test_mastery_progression():
    s = Settings(_env_file=None)
    from datetime import datetime
    m = Mastery(user_id=1, chunk_id=1, mastery=0.0, streak=0, correct_count=0, wrong_count=0)
    now = datetime(2026, 1, 1)
    assert desired_level(None, s) == "recall"
    apply_attempt(m, 1.0, now, s); apply_attempt(m, 1.0, now, s)
    assert m.streak == 2 and desired_level(m, s) == "apply"
    apply_attempt(m, 0.0, now, s)
    assert m.streak == 0 and m.due_at == now and m.wrong_count == 1


def test_vector_store_search_and_delete():
    st = NumpyVectorStore()
    v = np.eye(3, dtype=np.float32)
    st.add([10, 11, 12], v)
    assert st.search(v[1], 1)[0][0] == 11
    st.delete([11])
    assert 11 not in [i for i, _ in st.search(v[1], 3)]

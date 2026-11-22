"""Chunker và loader: ranh giới (đoạn quá dài, chồng lấn, chunk cuối ngắn, heading lồng, mã hoá lạ)."""


from app.modules.ingestion.chunker import _split_long, _tail, chunk_text, split_sections
from app.modules.ingestion.loaders import load_text


def test_nested_headings_are_joined_and_siblings_replace_each_other():
    text = "# A\n\nnội dung A\n\n## B\n\nnội dung B\n\n## C\n\nnội dung C\n\n# D\n\nnội dung D"
    assert [h for h, _ in split_sections(text)] == ["A", "A > B", "A > C", "D"]


def test_text_before_first_heading_has_empty_heading():
    assert split_sections("lời dẫn\n\n# A\n\nthân")[0][0] == ""


def test_long_paragraph_is_split_at_sentence_boundaries():
    para = " ".join(f"Đây là câu số {i} của đoạn rất dài." for i in range(40))
    parts = _split_long(para, 200)
    assert len(parts) > 1 and all(len(p) <= 200 for p in parts)
    assert all(p.endswith(".") for p in parts)  # không cắt giữa câu


def test_word_without_spaces_is_cut_hard():
    assert [len(p) for p in _split_long("x" * 250, 100)] == [100, 100, 50]


def test_short_paragraph_is_untouched():
    assert _split_long("ngắn thôi", 100) == ["ngắn thôi"]


def test_chunks_respect_max_size_and_overlap_between_neighbours():
    paras = [f"Đoạn {i}: " + "nội dung kiểm tra " * 6 for i in range(12)]
    chunks = chunk_text("# M\n\n" + "\n\n".join(paras), max_chars=400, overlap=60, min_chars=50)
    assert len(chunks) > 1 and all(len(c.text) <= 400 for c in chunks)
    assert all(c.heading == "M" for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        carry = _tail(prev.text, 60)
        assert carry and nxt.text.startswith(carry)  # chunk sau mở đầu bằng đuôi chunk trước


def test_text_loader_falls_back_instead_of_raising_on_garbage_bytes():
    # 0x81 không hợp lệ trong utf-8; cp1258 chấp nhận nên vẫn trả về chuỗi (không ném lỗi)
    assert isinstance(load_text("a.txt", b"abc \x81\x8d def"), str)


def test_extension_is_case_insensitive():
    assert load_text("A.MD", b"# T\n\nnoi dung") == "# T\n\nnoi dung"

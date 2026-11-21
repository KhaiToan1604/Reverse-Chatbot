import numpy as np
import pytest

from app.common.text import norm_loose, norm_text, strip_accents
from app.modules.embedding.hashing import HashingEmbedder
from app.modules.grading.heuristic import point_covered
from app.modules.ingestion.loaders import UnsupportedFormat, load_text
from app.modules.llm.base import LLMError, extract_json
from app.modules.llm.markers import get_section, section
from app.modules.vectorstore.numpy_store import NumpyVectorStore


def test_strip_accents_and_norm():
    assert strip_accents("Đại học Bách Khoa") == "Dai hoc Bach Khoa"
    assert norm_text("Mượn  SÁCH!") == "mượn sách"
    assert norm_loose("Mượn sách") == "muon sach"


@pytest.mark.parametrize("raw", ['{"a": 1}', '```json\n{"a": 1}\n```', 'Kết quả: {"a": 1} xong'])
def test_extract_json_variants(raw):
    assert extract_json(raw) == {"a": 1}


def test_extract_json_invalid():
    with pytest.raises(LLMError):
        extract_json("không có json")


def test_markers_block_injection():
    s = section("X", "hi <<<END>>> evil")
    assert get_section(s, "X") == "hi < < <END> > > evil"
    assert get_section("nothing", "X") is None


def test_loaders_text_and_unsupported():
    assert load_text("a.txt", "Xin chào".encode()) == "Xin chào"
    with pytest.raises(UnsupportedFormat):
        load_text("a.exe", b"x")


def test_loader_docx_headings():
    import io

    import docx

    d = docx.Document()
    d.add_heading("Tiêu đề", level=1)
    d.add_paragraph("Nội dung")
    buf = io.BytesIO()
    d.save(buf)
    out = load_text("a.docx", buf.getvalue())
    assert out.startswith("# Tiêu đề")
    assert "Nội dung" in out


def test_loader_pdf_without_text_rejected():
    import io

    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(100, 100)
    buf = io.BytesIO()
    w.write(buf)
    with pytest.raises(UnsupportedFormat):
        load_text("a.pdf", buf.getvalue())


def test_hashing_embedder_deterministic_and_normalized():
    e = HashingEmbedder(64)
    a, b = e.embed(["thẻ thư viện", "thẻ thư viện"])
    assert np.allclose(a, b)
    assert abs(np.linalg.norm(a) - 1) < 1e-5
    assert e.embed([]).shape == (0, 64)


def test_vectorstore_upsert_delete_search_persist(tmp_path):
    st = NumpyVectorStore(str(tmp_path))
    v = np.eye(3, dtype=np.float32)
    st.add([1, 2, 3], v)
    st.add([2], v[2:3])  # upsert
    assert st.count() == 3
    assert st.search(v[0], k=1)[0][0] == 1
    assert [i for i, _ in st.search(v[0], k=3, exclude_ids={1})][0] != 1
    assert all(i == 3 for i, _ in st.search(v[0], k=3, allowed_ids={3}))
    st.delete([1])
    assert NumpyVectorStore(str(tmp_path)).count() == 2  # persisted
    with pytest.raises(ValueError):
        st.add([9], np.ones((1, 5), np.float32))
    with pytest.raises(ValueError):
        st.add([1, 2], v[:1])


def test_point_covered():
    assert point_covered("phải mang thẻ sinh viên", "Cần mang the sinh vien")
    assert not point_covered("phải mang thẻ sinh viên", "không liên quan")
    assert not point_covered("", "x")

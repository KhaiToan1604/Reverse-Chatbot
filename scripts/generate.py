"""Sinh sẵn ngân sách câu hỏi (offline) để giảm gọi LLM lúc người dùng học.  Ví dụ:
    python -m scripts.generate --all
    python -m scripts.generate --document 1
"""

import argparse
import logging
import time

from sqlalchemy import select

from app.config import get_settings
from app.container import build_container
from app.db.base import create_all, init_engine, session_scope
from app.db.models import Chunk, Document


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--document", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="sinh lại cả những mục đã đủ câu hỏi (mặc định: chỉ sinh phần còn thiếu)")
    args = ap.parse_args()

    # Khởi tạo giống scripts/ingest.py. Sinh sẵn giúp người học không phải chờ LLM ở lần học đầu.
    s = get_settings()
    init_engine(s.database_url)
    create_all()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")  # hiện cảnh báo của LLM
    c = build_container(s)
    print(f"LLM: {c.llm.name} / {c.llm.model or '-'} | embedding: {c.embedder.name}", flush=True)
    if c.llm.name == "mock":
        print("Lưu ý: đang dùng LLM giả (LLM_PROVIDER=mock). Hãy kiểm tra file .env.", flush=True)
    with session_scope() as db:
        ids = list(db.scalars(select(Document.id))) if args.all else [args.document]
        for did in filter(None, ids):
            # Chạy từng chunk và in tiến trình ngay (gọi LLM thật có thể mất vài chục giây mỗi chunk).
            chunks = db.scalars(select(Chunk).where(Chunk.document_id == did).order_by(Chunk.position)).all()
            ok = bad = err = 0
            for i, ch in enumerate(chunks, 1):
                t0 = time.time()
                print(f"[doc {did}] chunk {i}/{len(chunks)} ...", end=" ", flush=True)
                rep = c.generation.generate_for_chunk(db, ch, only_missing=not args.force)
                db.commit()  # lưu ngay từng chunk: dừng giữa chừng vẫn giữ phần đã sinh
                ok, bad, err = ok + len(rep.created), bad + len(rep.rejected), err + len(rep.errors)
                print(f"hợp lệ={len(rep.created)} bị loại={len(rep.rejected)} lỗi={len(rep.errors)} ({time.time() - t0:.0f}s)", flush=True)
                for e in rep.errors[:2]:
                    print("   lỗi:", e, flush=True)
                if rep.rate_limited:
                    print(
                        "\nDỪNG: hết hạn mức gọi LLM (429). Đợi vài phút (hoặc sang ngày mới nếu hết quota ngày) rồi chạy lại "
                        "cùng lệnh: phần đã sinh được giữ, chỉ sinh phần còn thiếu.\n"
                        "Mẹo: đặt LLM_MIN_INTERVAL_S=6 trong .env để giãn cách; VALIDATE_QUESTIONS=false để giảm số lượt gọi.",
                        flush=True,
                    )
                    return
            print(f"[doc {did}] TỔNG hợp lệ={ok} bị loại={bad} lỗi={err}", flush=True)


if __name__ == "__main__":
    main()

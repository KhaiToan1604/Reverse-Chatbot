"""Sinh sẵn ngân sách câu hỏi (offline) để giảm gọi LLM lúc người dùng học.  Ví dụ:
    python -m scripts.generate --all
    python -m scripts.generate --document 1
"""

import argparse

from sqlalchemy import select

from app.config import get_settings
from app.container import build_container
from app.db.base import create_all, init_engine, session_scope
from app.db.models import Document


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--document", type=int)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    s = get_settings()
    init_engine(s.database_url)
    create_all()
    c = build_container(s)
    with session_scope() as db:
        ids = list(db.scalars(select(Document.id))) if args.all else [args.document]
        for did in filter(None, ids):
            rep = c.generation.generate_for_document(db, did)
            print(f"[doc {did}] hợp lệ={len(rep.created)} bị loại={len(rep.rejected)} lỗi={len(rep.errors)}")
            for e in rep.errors[:3]:
                print("   lỗi:", e)


if __name__ == "__main__":
    main()

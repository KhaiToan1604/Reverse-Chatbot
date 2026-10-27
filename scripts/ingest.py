"""Nạp tài liệu vào hệ thống.  Ví dụ:
    python -m scripts.ingest data/sample
    python -m scripts.ingest path/to/noi_quy.pdf --title "Nội quy thư viện"
"""

import argparse
from pathlib import Path

from app.config import get_settings
from app.container import build_container
from app.db.base import create_all, init_engine, session_scope
from app.modules.ingestion.loaders import SUPPORTED


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--title")
    args = ap.parse_args()

    s = get_settings()
    init_engine(s.database_url)
    create_all()
    c = build_container(s)
    p = Path(args.path)
    files = sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED) if p.is_dir() else [p]
    with session_scope() as db:
        for f in files:
            res = c.ingestion.ingest_bytes(db, f.name, f.read_bytes(), args.title if len(files) == 1 else None)
            note = " (đã có, bỏ qua)" if res.already_existed else ""
            print(f"[doc {res.document.id}] {f.name}: {res.num_chunks} chunk{note}")


if __name__ == "__main__":
    main()

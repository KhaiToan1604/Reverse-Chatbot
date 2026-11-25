"""Xem câu hỏi đã sinh (mặc định: câu bị loại) để biết LLM sai ở đâu.  Ví dụ:
    python -m scripts.inspect_questions                       # 5 câu bị loại đầu tiên
    python -m scripts.inspect_questions --qtype mcq --limit 3
    python -m scripts.inspect_questions --status valid --qtype fill_blank
"""

import argparse
import json

from sqlalchemy import select

from app.config import get_settings
from app.db.base import create_all, init_engine, session_scope
from app.db.models import Question


def main() -> None:
    """In các câu hỏi gần nhất theo bộ lọc (--status, --qtype, --limit); chỉ đọc, không sửa dữ liệu."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", default="rejected", choices=["rejected", "valid"])
    ap.add_argument("--qtype", choices=["mcq", "fill_blank", "short_answer", "scenario"])
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    s = get_settings()
    init_engine(s.database_url)
    create_all()
    with session_scope() as db:
        stmt = select(Question).where(Question.status == args.status).order_by(Question.id.desc()).limit(args.limit)
        if args.qtype:
            stmt = stmt.where(Question.qtype == args.qtype)
        rows = db.scalars(stmt).all()
        if not rows:
            print("Không có câu nào khớp.")
        for q in rows:
            print(f"--- câu #{q.id} | {q.qtype}/{q.level} | trạng thái: {q.status} | model: {q.model}")
            if q.reject_reason:
                print(f"lý do loại : {q.reject_reason}")
            print(f"câu hỏi    : {q.question}")
            print(f"options    : {json.dumps(q.options, ensure_ascii=False)}")  # None = LLM không trả lựa chọn
            print(f"đáp án     : {q.answer}")
            print(f"trích dẫn  : {q.source_quote}")


if __name__ == "__main__":
    main()

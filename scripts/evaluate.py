"""Chạy các phép đánh giá cho báo cáo.  Ví dụ:
    python -m scripts.evaluate report
    python -m scripts.evaluate purge-duplicates   # xoá câu bị loại vì trùng (do chạy sinh lặp lại)
    python -m scripts.evaluate export-review reviews.csv --n 50
    python -m scripts.evaluate import-review reviews.csv
    python -m scripts.evaluate grader graded_answers.csv
    python -m scripts.evaluate rag-vs-norag --chunks 10
"""

import argparse
import json

from app.config import get_settings
from app.container import build_container
from app.db.base import create_all, init_engine, session_scope
from app.modules.evaluation import runner


def main() -> None:
    """Đọc tham số dòng lệnh, chạy đúng một phép đánh giá và in kết quả JSON. Thêm phép đo mới: thêm subparser + nhánh `elif`."""
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report")
    sub.add_parser("purge-duplicates")
    p = sub.add_parser("export-review")
    p.add_argument("path")
    p.add_argument("--n", type=int, default=50)
    p = sub.add_parser("import-review")
    p.add_argument("path")
    p = sub.add_parser("grader")
    p.add_argument("path")
    p = sub.add_parser("rag-vs-norag")
    p.add_argument("--chunks", type=int, default=10)
    args = ap.parse_args()

    # Mỗi lệnh con ứng với một hàm trong app/modules/evaluation/runner.py; kết quả in ra dạng JSON để dán vào báo cáo.
    s = get_settings()
    init_engine(s.database_url)
    create_all()
    c = build_container(s)
    with session_scope() as db:
        if args.cmd == "report":
            out = runner.question_quality_report(db)
        elif args.cmd == "purge-duplicates":
            out = {"deleted_duplicate_rejects": runner.purge_duplicate_rejects(db)}
        elif args.cmd == "export-review":
            out = {"exported": runner.export_review_csv(db, args.path, args.n)}
        elif args.cmd == "import-review":
            out = runner.import_review_labels(args.path)
        elif args.cmd == "grader":
            out = runner.grader_agreement(db, c.grader, args.path, s.pass_threshold)
        else:
            out = runner.rag_vs_norag(db, c.generation, args.chunks)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

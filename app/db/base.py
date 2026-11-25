"""Kết nối CSDL (SQLAlchemy) dùng chung toàn ứng dụng.

Engine và sessionmaker là biến toàn cục của module: `init_engine` đặt, `dispose_engine` huỷ.
API dùng `get_db` (một phiên cho mỗi request); script/CLI dùng `session_scope`.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Lớp cơ sở của mọi bảng trong models.py."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(database_url: str) -> Engine:
    """Khởi tạo engine và sessionmaker toàn cục (gọi lại sẽ thay engine cũ). `database_url` lấy từ Settings.database_url."""
    global _engine, _SessionLocal
    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {}
    # SQLite mặc định cấm dùng kết nối ở thread khác; FastAPI chạy request ở nhiều thread nên phải tắt kiểm tra.
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    # DB trong bộ nhớ chỉ tồn tại trong một kết nối -> dùng StaticPool để mọi nơi dùng chung kết nối đó.
    if ":memory:" in database_url:
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    _engine = create_engine(database_url, **kwargs)
    # expire_on_commit=False: đối tượng vẫn đọc được sau commit (không bị nạp lại).
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def dispose_engine() -> None:
    """Đóng mọi kết nối (gọi khi tắt app) để không rò rỉ kết nối SQLite; sau đó phải gọi lại `init_engine` mới dùng được DB."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def create_all() -> None:
    """Tạo các bảng nếu chưa có (chưa dùng migration).

    Muốn thêm cột/bảng: sửa app/db/models.py. Với DB đã có dữ liệu, `create_all` KHÔNG thêm cột vào bảng cũ: cần xoá data/app.db
    (rồi nạp lại tài liệu) hoặc dùng Alembic.
    """
    from app.db import models  # noqa: F401  (đăng ký bảng)

    assert _engine is not None, "init_engine() chưa được gọi"
    Base.metadata.create_all(_engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: mỗi request một phiên (Session), tự đóng khi xong. Cần `db.commit()` tay nếu có ghi dữ liệu."""
    assert _SessionLocal is not None, "init_engine() chưa được gọi"
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Dùng cho script/CLI: tự commit khi thành công, rollback khi có lỗi."""
    assert _SessionLocal is not None, "init_engine() chưa được gọi"
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

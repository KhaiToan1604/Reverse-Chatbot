from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(database_url: str) -> Engine:
    """Khởi tạo engine (gọi lại để đổi DB, ví dụ trong test)."""
    global _engine, _SessionLocal
    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in database_url:
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    _engine = create_engine(database_url, **kwargs)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def create_all() -> None:
    from app.db import models  # noqa: F401  (đăng ký bảng)

    assert _engine is not None, "init_engine() chưa được gọi"
    Base.metadata.create_all(_engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    assert _SessionLocal is not None, "init_engine() chưa được gọi"
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Dùng cho script/CLI."""
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

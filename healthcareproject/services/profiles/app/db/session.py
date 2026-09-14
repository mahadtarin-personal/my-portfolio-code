from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

settings = get_settings()

_connect_args: dict[str, object] = {}
_engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    # Lets tests run against an in-memory SQLite DB with a single shared
    # connection instead of a real Postgres instance.
    _connect_args["check_same_thread"] = False
    _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(settings.database_url, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Commit-scoped session for code with no FastAPI request boundary to
    commit on its behalf — used by the outbox relay, which runs in a
    separate worker process. Same helper booking has had since its
    Temporal activities needed it; profiles didn't need one until the
    outbox relay came along."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

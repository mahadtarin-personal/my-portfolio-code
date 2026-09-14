from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """INSERT-only, hash-chained (design §13): each row's `hash` covers
    its own fields plus the previous row's `hash`, so altering any past
    row (even via direct DB access, if the INSERT-only role grant were
    ever bypassed) breaks every hash after it — detectable by
    app/services/hash_chain.py::verify_chain(). The actual tamper
    *prevention* is a DB-level grant (see deploy/postgres/audit-grants.sql):
    the role this service connects as has SELECT+INSERT only, no
    UPDATE/DELETE — enforced by Postgres itself, not application code.

    `id` is a plain autoincrementing integer, not a UUID like every other
    model in this project — deliberately, because the hash chain needs an
    unambiguous, strictly monotonic "previous row" and a DB sequence
    guarantees that; a UUID doesn't carry ordering information at all."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

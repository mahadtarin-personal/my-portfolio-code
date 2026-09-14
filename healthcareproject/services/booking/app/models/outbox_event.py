import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxEvent(Base):
    """The outbox side of the outbox pattern: written in the SAME
    transaction as whatever business change produced it (see
    app/services/events.py::publish), so it commits or rolls back
    atomically together — no "the appointment confirmed but the event
    silently vanished because Kafka was down" gap. A separate relay
    process (app/outbox_relay.py) is the only thing that actually talks
    to Kafka, draining rows where published_at IS NULL.

    `id` is a plain autoincrementing integer, not a UUID like most models
    here — the relay processes rows in insertion order, and a DB sequence
    gives that for free; `event_id` (UUID) is the identity that actually
    goes out in the Kafka envelope."""

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    topic: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

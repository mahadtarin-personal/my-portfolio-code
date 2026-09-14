import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxEvent(Base):
    """The outbox side of the outbox pattern — see
    services/booking/app/models/outbox_event.py for the full rationale
    (same design, same reasoning, mirrored in this service). Written in
    the SAME transaction as whatever business change produced it, so it
    commits or rolls back atomically together; app/outbox_relay.py is the
    only thing that actually talks to Kafka."""

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

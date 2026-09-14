import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalyticsEvent(Base):
    """One row per Kafka event this service reacted to — raw storage, not
    pre-aggregated. Unique on event_id, same dedup mechanism as
    notification/audit: a redelivered event (Kafka's at-least-once
    guarantee, or a consumer crash before the offset commits) hits the
    unique constraint instead of being double-counted in the metrics.

    Metrics are computed on read (see crud.analytics_event.compute_metrics)
    from these raw rows rather than kept as running counters — same
    "derive a view from stored facts" approach audit uses for hash-chain
    verification, and it means a metric definition can change without a
    backfill or migration."""

    __tablename__ = "analytics_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_analytics_events_event_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

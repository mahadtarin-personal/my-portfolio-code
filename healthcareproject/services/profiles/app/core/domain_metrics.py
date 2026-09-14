from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.outbox_event import OutboxEvent


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def compute_outbox_metrics() -> dict[str, tuple[str, float]]:
    """Outbox lag — the thing that's normally invisible. The outbox
    pattern (see app/services/events.py) is deliberately fail-open: a
    Kafka outage never breaks a request, the row just sits unpublished
    until profiles-outbox-relay can deliver it. That's great for
    resilience and terrible for visibility — without this, nobody would
    know Kafka's been down for an hour unless they went digging with
    psql, exactly like we did live once. Queried fresh on every
    Prometheus scrape (register_gauge_collector), not cached — this
    query is cheap (one COUNT, one MIN over an indexed column)."""
    with SessionLocal() as db:
        unpublished = (
            db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
            )
            or 0
        )
        oldest = db.scalar(
            select(func.min(OutboxEvent.created_at)).where(OutboxEvent.published_at.is_(None))
        )

    age_seconds = (datetime.now(timezone.utc) - _as_utc(oldest)).total_seconds() if oldest else 0.0

    return {
        "smarthealth_outbox_unpublished_events": (
            "Outbox rows not yet published to Kafka",
            float(unpublished),
        ),
        "smarthealth_outbox_oldest_unpublished_age_seconds": (
            "Age in seconds of the oldest unpublished outbox row (0 if none)",
            age_seconds,
        ),
    }

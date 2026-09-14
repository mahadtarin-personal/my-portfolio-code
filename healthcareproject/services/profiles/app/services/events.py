from __future__ import annotations

from kafka_shared import Topic
from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEvent


def publish(db: Session, event_type: Topic, payload: dict, *, actor: str | None = None) -> None:
    """Outbox pattern — see services/booking/app/services/events.py for
    the full rationale (identical design, mirrored in this service).
    Writes to outbox_events using the CALLER's own session, so it commits
    atomically with whatever business change triggered it.
    app/outbox_relay.py is the only thing that actually talks to Kafka —
    no kafka_enabled check belongs here, since this never touches Kafka.

    Must be called BEFORE the caller's db.commit() — not after — for the
    atomicity guarantee to actually hold."""
    db.add(OutboxEvent(topic=event_type.value, actor=actor, payload=payload))

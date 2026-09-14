from __future__ import annotations

from kafka_shared import Topic
from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEvent


def publish(db: Session, event_type: Topic, payload: dict, *, actor: str | None = None) -> None:
    """Outbox pattern, not a direct Kafka call: writes a row into
    outbox_events using the CALLER's own session — so it commits (or
    rolls back) atomically together with whatever business change
    triggered it, in the same transaction. app/outbox_relay.py is the
    only thing that actually talks to Kafka, draining unpublished rows
    on its own schedule.

    This closes a real gap the fire-and-forget version had: if Kafka
    were unreachable at the moment of a direct publish call, the event
    would just be silently lost — the business change would still commit
    successfully, but nothing would ever know an event was supposed to
    go out. Writing to this service's own database can't fail
    independently of the business change it's paired with, and the
    relay retries indefinitely once Kafka comes back.

    No kafka_enabled check here (unlike the old direct-publish version) —
    this never talks to Kafka at all, only this service's own database,
    so there's nothing to gate. The kill switch belongs on the relay
    (app/outbox_relay.py::main), which is the thing that actually depends
    on Kafka being reachable.

    Must be called BEFORE the caller's db.commit() — not after — for the
    atomicity guarantee to actually hold."""
    db.add(OutboxEvent(topic=event_type.value, actor=actor, payload=payload))

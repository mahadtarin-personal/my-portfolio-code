import uuid
from datetime import datetime, timezone

from kafka_shared import EventEnvelope, Topic

from app import crud
from app.handlers import handle_event


def _envelope(event_type: Topic, *, actor: str | None = None, payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
        actor=actor,
        payload=payload or {},
    )


def test_handle_event_records_any_topic(db) -> None:
    envelope = _envelope(Topic.CONSENT_UPDATED, actor="patient-1", payload={"consent": True})
    handle_event(envelope)

    rows = crud.audit_log.list_recent(db)
    assert len(rows) == 1
    assert rows[0].event_type == "consent.updated"
    assert rows[0].actor == "patient-1"


def test_handle_event_is_idempotent_on_replay(db) -> None:
    envelope = _envelope(Topic.PROVIDER_SCHEDULE_CHANGED, actor="provider-1")
    handle_event(envelope)
    handle_event(envelope)

    assert len(crud.audit_log.list_recent(db)) == 1


def test_handle_event_chains_across_multiple_topics(db) -> None:
    handle_event(_envelope(Topic.USER_LOGGED_IN, actor="u1"))
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED, actor="u1"))
    handle_event(_envelope(Topic.APPOINTMENT_CANCELLED, actor="u1"))

    valid, broken_at_id, rows_checked = crud.audit_log.verify_chain(db)
    assert valid is True
    assert rows_checked == 3

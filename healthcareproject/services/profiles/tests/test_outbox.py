from kafka_shared import Topic
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.outbox_event import OutboxEvent
from app.outbox_relay import relay_once
from app.services.events import publish


def test_outbox_write_commits_with_its_transaction(db) -> None:
    publish(db, Topic.PATIENT_REGISTERED, {"patient_id": "p1"}, actor="p1")
    db.commit()

    rows = list(db.scalars(select(OutboxEvent)))
    assert len(rows) == 1
    assert rows[0].topic == "patient.registered"
    assert rows[0].published_at is None


def test_outbox_write_rolls_back_with_its_transaction(db) -> None:
    publish(db, Topic.PATIENT_REGISTERED, {"patient_id": "p1"}, actor="p1")
    db.rollback()

    rows = list(db.scalars(select(OutboxEvent)))
    assert len(rows) == 0


def test_relay_once_publishes_unpublished_rows_and_marks_them(db, monkeypatch) -> None:
    publish(db, Topic.USER_LOGGED_IN, {"user_id": "u1"}, actor="u1")
    db.commit()

    calls = []

    def _fake_publish_event_sync(bootstrap_servers, topic, payload, *, actor=None, event_id=None):
        calls.append((topic, payload, actor, event_id))
        return True

    monkeypatch.setattr("app.outbox_relay.publish_event_sync", _fake_publish_event_sync)

    count = relay_once()
    assert count == 1
    assert calls[0][0] == Topic.USER_LOGGED_IN

    fresh_db = SessionLocal()
    try:
        row = fresh_db.scalars(select(OutboxEvent)).first()
        assert row.published_at is not None
        assert row.event_id == calls[0][3]
    finally:
        fresh_db.close()


def test_relay_once_recovers_once_kafka_comes_back(db, monkeypatch) -> None:
    publish(db, Topic.PROVIDER_SCHEDULE_CHANGED, {"provider_id": "pr1"}, actor="pr1")
    db.commit()

    monkeypatch.setattr("app.outbox_relay.publish_event_sync", lambda *a, **kw: False)
    assert relay_once() == 0

    monkeypatch.setattr("app.outbox_relay.publish_event_sync", lambda *a, **kw: True)
    assert relay_once() == 1

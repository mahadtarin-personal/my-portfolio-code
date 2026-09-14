from kafka_shared import Topic
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.outbox_event import OutboxEvent
from app.outbox_relay import relay_once
from app.services.events import publish


def test_outbox_write_commits_with_its_transaction(db) -> None:
    publish(db, Topic.APPOINTMENT_BOOKED, {"a": 1}, actor="p1")
    db.commit()

    rows = list(db.scalars(select(OutboxEvent)))
    assert len(rows) == 1
    assert rows[0].topic == "appointment.booked"
    assert rows[0].published_at is None


def test_outbox_write_rolls_back_with_its_transaction(db) -> None:
    # This is the whole point: an outbox row can never exist for a
    # business change that didn't actually happen — they're the same
    # transaction, not two separate steps that can diverge.
    publish(db, Topic.APPOINTMENT_BOOKED, {"a": 1}, actor="p1")
    db.rollback()

    rows = list(db.scalars(select(OutboxEvent)))
    assert len(rows) == 0


def test_relay_once_publishes_unpublished_rows_and_marks_them(db, monkeypatch) -> None:
    publish(db, Topic.APPOINTMENT_BOOKED, {"a": 1}, actor="p1")
    db.commit()

    calls = []

    def _fake_publish_event_sync(bootstrap_servers, topic, payload, *, actor=None, event_id=None):
        calls.append((topic, payload, actor, event_id))
        return True

    monkeypatch.setattr("app.outbox_relay.publish_event_sync", _fake_publish_event_sync)

    count = relay_once()
    assert count == 1
    assert len(calls) == 1
    topic, payload, actor, event_id = calls[0]
    assert topic == Topic.APPOINTMENT_BOOKED
    assert payload == {"a": 1}
    assert actor == "p1"

    fresh_db = SessionLocal()
    try:
        row = fresh_db.scalars(select(OutboxEvent)).first()
        assert row.published_at is not None
        assert row.event_id == event_id  # the relay reuses the outbox row's own id
    finally:
        fresh_db.close()


def test_relay_once_leaves_row_unpublished_on_delivery_failure(db, monkeypatch) -> None:
    publish(db, Topic.APPOINTMENT_BOOKED, {"a": 1}, actor="p1")
    db.commit()

    monkeypatch.setattr("app.outbox_relay.publish_event_sync", lambda *a, **kw: False)

    count = relay_once()
    assert count == 0

    fresh_db = SessionLocal()
    try:
        row = fresh_db.scalars(select(OutboxEvent)).first()
        assert row.published_at is None
    finally:
        fresh_db.close()


def test_relay_once_recovers_once_kafka_comes_back(db, monkeypatch) -> None:
    # The actual outage-recovery guarantee, in miniature: a failed relay
    # attempt doesn't lose the event — it's still there, unpublished, and
    # the very next successful cycle picks it up.
    publish(db, Topic.APPOINTMENT_BOOKED, {"a": 1}, actor="p1")
    db.commit()

    monkeypatch.setattr("app.outbox_relay.publish_event_sync", lambda *a, **kw: False)
    assert relay_once() == 0

    monkeypatch.setattr("app.outbox_relay.publish_event_sync", lambda *a, **kw: True)
    assert relay_once() == 1


def test_relay_once_does_not_republish_already_published_rows(db, monkeypatch) -> None:
    publish(db, Topic.APPOINTMENT_BOOKED, {"a": 1}, actor="p1")
    db.commit()

    calls = []
    monkeypatch.setattr(
        "app.outbox_relay.publish_event_sync",
        lambda *a, **kw: (calls.append(1), True)[1],
    )

    assert relay_once() == 1
    assert relay_once() == 0  # nothing left to relay
    assert len(calls) == 1

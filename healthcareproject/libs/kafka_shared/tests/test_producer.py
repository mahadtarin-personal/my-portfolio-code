import uuid
from datetime import datetime, timezone

import pytest

from kafka_shared import EventEnvelope, Topic, get_producer, publish_event, publish_event_sync
from kafka_shared.producer import _producers


@pytest.fixture(autouse=True)
def _clear_producer_cache():
    _producers.clear()
    yield
    _producers.clear()


def test_event_envelope_round_trips_through_json() -> None:
    envelope = EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type=Topic.APPOINTMENT_BOOKED,
        occurred_at=datetime.now(timezone.utc),
        actor="patient-1",
        payload={"appointment_id": "abc"},
    )
    restored = EventEnvelope.model_validate_json(envelope.model_dump_json())
    assert restored.event_type == Topic.APPOINTMENT_BOOKED
    assert restored.payload == {"appointment_id": "abc"}


def test_get_producer_memoizes_per_bootstrap_servers() -> None:
    a = get_producer("localhost:9092")
    b = get_producer("localhost:9092")
    c = get_producer("otherhost:9092")
    assert a is b
    assert a is not c


def test_publish_event_does_not_raise_when_broker_unreachable() -> None:
    # confluent-kafka's Producer connects lazily/async on a background
    # thread — instantiating it and calling produce() against a
    # nonexistent broker must return immediately, not raise or block.
    # Delivery failure only ever surfaces via the async callback.
    publish_event(
        "nonexistent-host:9092",
        Topic.APPOINTMENT_BOOKED,
        {"appointment_id": "abc"},
        actor="patient-1",
    )


def test_publish_event_swallows_buffer_error(monkeypatch) -> None:
    class _FullQueueProducer:
        def produce(self, *args, **kwargs):
            raise BufferError("queue full")

        def poll(self, timeout):
            return 0

    monkeypatch.setattr(
        "kafka_shared.producer.get_producer", lambda bootstrap_servers: _FullQueueProducer()
    )
    publish_event("localhost:9092", Topic.USER_LOGGED_IN, {"user_id": "u1"})  # must not raise


def test_publish_event_sync_returns_true_on_confirmed_delivery(monkeypatch) -> None:
    class _SuccessProducer:
        def produce(self, topic, key, value, callback):
            callback(None, None)  # simulate immediate successful delivery

        def flush(self, timeout):
            return 0  # nothing left undelivered

    monkeypatch.setattr(
        "kafka_shared.producer.get_producer", lambda bootstrap_servers: _SuccessProducer()
    )
    result = publish_event_sync("localhost:9092", Topic.APPOINTMENT_BOOKED, {"a": 1}, event_id="e1")
    assert result is True


def test_publish_event_sync_returns_false_on_delivery_failure(monkeypatch) -> None:
    class _FailureProducer:
        def produce(self, topic, key, value, callback):
            callback(Exception("broker down"), None)

        def flush(self, timeout):
            return 0

    monkeypatch.setattr(
        "kafka_shared.producer.get_producer", lambda bootstrap_servers: _FailureProducer()
    )
    result = publish_event_sync("localhost:9092", Topic.APPOINTMENT_BOOKED, {"a": 1}, event_id="e1")
    assert result is False


def test_publish_event_sync_returns_false_when_flush_times_out(monkeypatch) -> None:
    class _StuckProducer:
        def produce(self, topic, key, value, callback):
            pass  # never calls the callback — simulates an unreachable broker

        def flush(self, timeout):
            return 1  # one message still undelivered when the timeout hit

    monkeypatch.setattr(
        "kafka_shared.producer.get_producer", lambda bootstrap_servers: _StuckProducer()
    )
    result = publish_event_sync(
        "localhost:9092", Topic.APPOINTMENT_BOOKED, {"a": 1}, event_id="e1", timeout=0.1
    )
    assert result is False


def test_publish_event_sync_reuses_the_given_event_id(monkeypatch) -> None:
    captured = {}

    class _CapturingProducer:
        def produce(self, topic, key, value, callback):
            captured["key"] = key
            callback(None, None)

        def flush(self, timeout):
            return 0

    monkeypatch.setattr(
        "kafka_shared.producer.get_producer", lambda bootstrap_servers: _CapturingProducer()
    )
    publish_event_sync(
        "localhost:9092", Topic.APPOINTMENT_BOOKED, {"a": 1}, event_id="outbox-row-42"
    )
    assert captured["key"] == "outbox-row-42"

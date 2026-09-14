from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from confluent_kafka import KafkaException, Producer

from .events import EventEnvelope, Topic

logger = logging.getLogger(__name__)

_producers: dict[str, Producer] = {}


def get_producer(bootstrap_servers: str) -> Producer:
    """One Producer per bootstrap_servers string, memoized for the life of
    the process — a Producer owns a background thread and connection
    pool, so reusing one is both cheaper and lets librdkafka batch
    deliveries instead of opening a new connection per publish."""
    if bootstrap_servers not in _producers:
        _producers[bootstrap_servers] = Producer({"bootstrap.servers": bootstrap_servers})
    return _producers[bootstrap_servers]


def _delivery_callback(err, msg) -> None:
    if err is not None:
        logger.warning("event delivery failed: topic=%s error=%s", msg.topic() if msg else "?", err)


def publish_event(
    bootstrap_servers: str,
    event_type: Topic,
    payload: dict,
    *,
    actor: str | None = None,
) -> None:
    """Fire-and-forget — never blocks the caller waiting on the broker.

    confluent-kafka's Producer.produce() only queues the message locally;
    the actual network send happens on librdkafka's own background
    thread, so an unreachable Kafka never hangs the calling request the
    way a synchronous HTTP/Redis call would — the exact failure mode
    found and fixed twice already in this project (see
    booking/app/core/cache.py and
    profiles/app/services/slot_reconciliation.py, both of which needed an
    explicit thread+timeout workaround because their underlying clients
    *do* block). A full local queue is the one thing that can raise
    synchronously here — caught and logged, never re-raised, so
    publishing an event can never break the write it's attached to.
    """
    envelope = EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
        actor=actor,
        payload=payload,
    )
    producer = get_producer(bootstrap_servers)
    try:
        producer.produce(
            event_type.value,
            key=envelope.event_id,
            value=envelope.model_dump_json(),
            callback=_delivery_callback,
        )
        producer.poll(0)  # services delivery-report callbacks; does not block on network
    except (KafkaException, BufferError):
        logger.warning("failed to enqueue event %s", event_type.value, exc_info=True)


def publish_event_sync(
    bootstrap_servers: str,
    event_type: Topic,
    payload: dict,
    *,
    actor: str | None = None,
    event_id: str | None = None,
    timeout: float = 10.0,
) -> bool:
    """Blocking, confirmed-delivery publish — the deliberate exception to
    publish_event()'s fire-and-forget rule, used only by an outbox relay
    (which isn't on any user-facing request path, so it can afford to
    wait) that needs to actually KNOW delivery succeeded before marking
    an outbox row as published. Returns True only once Kafka has
    genuinely acknowledged the message, not just accepted it into the
    local queue.

    `event_id` lets the caller reuse an existing id (the outbox row's own
    id) instead of minting a fresh one — the event published to Kafka
    should carry the same identity as the durable record that produced
    it, both for tracing and so consumer-side dedup means what it says.
    """
    envelope = EventEnvelope(
        event_id=event_id or str(uuid.uuid4()),
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
        actor=actor,
        payload=payload,
    )
    producer = get_producer(bootstrap_servers)
    delivered = {"ok": False}

    def _callback(err, msg) -> None:
        delivered["ok"] = err is None
        if err is not None:
            logger.warning("sync publish delivery failed: topic=%s error=%s", event_type.value, err)

    try:
        producer.produce(
            event_type.value,
            key=envelope.event_id,
            value=envelope.model_dump_json(),
            callback=_callback,
        )
    except (KafkaException, BufferError):
        logger.warning("sync publish failed to enqueue event %s", event_type.value, exc_info=True)
        return False

    remaining = producer.flush(timeout)
    if remaining > 0:
        logger.warning(
            "sync publish timed out after %.1fs, %d message(s) still undelivered", timeout, remaining
        )
        return False
    return delivered["ok"]

from __future__ import annotations

import logging
import signal
from collections.abc import Callable

from confluent_kafka import Consumer, KafkaError

from .events import EventEnvelope

logger = logging.getLogger(__name__)


def run_consumer_loop(
    bootstrap_servers: str,
    group_id: str,
    topics: list[str],
    handler: Callable[[EventEnvelope], None],
    *,
    poll_timeout: float = 1.0,
) -> None:
    """Blocking poll loop — run this as a worker process's main(), same
    shape as booking's app/worker.py Temporal loop. Commits the offset
    only after handler() returns without raising, so a crash mid-handler
    redelivers the event on restart instead of silently dropping it — the
    handler's own job is to dedupe on event_id (design §8), not to rely
    on Kafka delivering exactly once."""
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(topics)
    running = True

    def _stop(*_args) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        while running:
            msg = consumer.poll(poll_timeout)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.warning("consumer error: %s", msg.error())
                continue
            try:
                envelope = EventEnvelope.model_validate_json(msg.value())
                handler(envelope)
            except Exception:
                logger.exception("event handler failed for topic=%s", msg.topic())
                continue  # don't commit — redelivered on restart
            consumer.commit(msg)
    finally:
        consumer.close()

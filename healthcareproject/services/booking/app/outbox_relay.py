from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from kafka_shared import Topic, publish_event_sync
from logging_shared import configure_logging
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.outbox_event import OutboxEvent

configure_logging("booking-outbox-relay")
logger = logging.getLogger("booking.outbox_relay")

POLL_INTERVAL_SECONDS = 2.0


def relay_once() -> int:
    """One poll cycle. Commits each row's published_at individually
    (not the whole batch in one transaction) — if the process dies
    mid-cycle, only the one row currently in flight risks a duplicate
    publish on restart, and that's harmless: it reuses the same event_id,
    which every consumer already dedupes on (design §8). Returns how
    many rows were successfully relayed."""
    settings = get_settings()
    with session_scope() as db:
        row_ids = list(
            db.scalars(
                select(OutboxEvent.id)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.id)
            )
        )

    published = 0
    for row_id in row_ids:
        with session_scope() as db:
            row = db.get(OutboxEvent, row_id)
            if row is None or row.published_at is not None:
                continue  # already handled by a previous cycle
            ok = publish_event_sync(
                settings.kafka_bootstrap_servers,
                Topic(row.topic),
                row.payload,
                actor=row.actor,
                event_id=row.event_id,
            )
            if ok:
                row.published_at = datetime.now(timezone.utc)
                published += 1
            else:
                logger.warning(
                    "failed to relay outbox event id=%s topic=%s — will retry next cycle",
                    row.id,
                    row.topic,
                )
    return published


def main() -> None:
    settings = get_settings()
    if not settings.kafka_enabled:
        logger.info("kafka_enabled=false — outbox relay not starting")
        return
    logger.info(
        "booking outbox relay started; bootstrap=%s poll_interval=%ss",
        settings.kafka_bootstrap_servers,
        POLL_INTERVAL_SECONDS,
    )
    while True:
        try:
            count = relay_once()
            if count:
                logger.info("relayed %d outbox event(s)", count)
        except Exception:
            logger.exception("outbox relay iteration failed")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

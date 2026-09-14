from __future__ import annotations

import logging

from kafka_shared import EventEnvelope

from app.crud import analytics_event as analytics_crud
from app.db.session import session_scope

logger = logging.getLogger(__name__)


def handle_event(envelope: EventEnvelope) -> None:
    with session_scope() as db:
        if analytics_crud.already_processed(db, envelope.event_id):
            logger.info("skipping already-processed event %s", envelope.event_id)
            return

        analytics_crud.record(
            db,
            event_id=envelope.event_id,
            event_type=envelope.event_type.value,
            actor=envelope.actor,
            payload=envelope.payload,
        )
        logger.info("recorded %s for metrics", envelope.event_type.value)

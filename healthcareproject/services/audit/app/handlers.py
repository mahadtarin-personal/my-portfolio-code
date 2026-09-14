from __future__ import annotations

import logging

from kafka_shared import EventEnvelope

from app.crud import audit_log as audit_log_crud
from app.db.session import session_scope

logger = logging.getLogger(__name__)


def handle_event(envelope: EventEnvelope) -> None:
    """Audit consumes every event type — its whole job is a complete
    tamper-evident record, unlike notification/analytics which only care
    about a relevant subset."""
    with session_scope() as db:
        if audit_log_crud.already_processed(db, envelope.event_id):
            logger.info("skipping already-processed event %s", envelope.event_id)
            return
        row = audit_log_crud.append(
            db,
            event_id=envelope.event_id,
            event_type=envelope.event_type.value,
            actor=envelope.actor,
            payload=envelope.payload,
        )
        if row is not None:
            logger.info("recorded audit entry id=%s type=%s", row.id, row.event_type)

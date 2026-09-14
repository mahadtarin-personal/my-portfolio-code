from __future__ import annotations

import logging

from kafka_shared import EventEnvelope, Topic

from app.crud import notification as notification_crud
from app.db.session import session_scope
from app.models.notification import NotificationChannel, NotificationStatus

logger = logging.getLogger(__name__)

# STUBBED content — no real email/SMS provider integration, same pattern
# as billing_precheck's stub in booking. Structured so a real provider
# call drops in here later without changing the event contract or the
# dedup/storage logic around it.
_MESSAGES: dict[Topic, str] = {
    Topic.APPOINTMENT_BOOKED: "Your appointment is confirmed.",
    Topic.APPOINTMENT_CANCELLED: "Your appointment has been cancelled.",
    Topic.APPOINTMENT_RESCHEDULED: "Your appointment has been rescheduled.",
    Topic.REMINDER_SCHEDULED: "Reminder: you have an upcoming appointment.",
    Topic.BILLING_STATUS_UPDATED: "Your billing status has been updated.",
}


def handle_event(envelope: EventEnvelope) -> None:
    with session_scope() as db:
        if notification_crud.already_processed(db, envelope.event_id):
            logger.info("skipping already-processed event %s", envelope.event_id)
            return

        recipient = envelope.actor or envelope.payload.get("patient_id") or "unknown"
        message = _MESSAGES.get(envelope.event_type, f"Update: {envelope.event_type.value}")

        notification_crud.record(
            db,
            event_id=envelope.event_id,
            event_type=envelope.event_type.value,
            recipient=recipient,
            channel=NotificationChannel.EMAIL,
            status=NotificationStatus.SENT,
            message=message,
        )
        logger.info("notified %s: %s", recipient, message)

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel


class Topic(str, enum.Enum):
    """The 13 Kafka events named in the design doc (§4) — kept as an enum,
    same convention as Role/AppointmentStatus/SlotStatus elsewhere in this
    project. The topic name IS the event type: one topic per event, so a
    consumer just subscribes to exactly what it cares about instead of
    filtering an event_type field out of a shared firehose topic."""

    APPOINTMENT_BOOKED = "appointment.booked"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    SCHEDULE_CONFLICT_RESOLVED = "schedule_conflict.resolved"
    PROVIDER_SCHEDULE_CHANGED = "provider.schedule_changed"
    REMINDER_SCHEDULED = "reminder.scheduled"
    BILLING_STATUS_UPDATED = "billing.status_updated"
    VISIT_COMPLETED = "visit.completed"
    ANALYTICS_PROCESSED = "analytics.processed"
    CLINICAL_RESULT_ADDED = "clinical.result_added"
    USER_LOGGED_IN = "user.logged_in"
    USER_LOGIN_FAILED = "user.login_failed"
    PATIENT_REGISTERED = "patient.registered"
    CONSENT_UPDATED = "consent.updated"


class EventEnvelope(BaseModel):
    """Every event published has this shape. `event_id` is what consumers
    dedupe on (design §8 — "Kafka consumers dedupe by the event's own
    unique ID, set at publish time, not our HTTP-level idempotency key").
    `actor`/`payload` match audit_log's columns directly (§13) so Audit can
    store an event with no transformation."""

    event_id: str
    event_type: Topic
    occurred_at: datetime
    actor: str | None = None
    payload: dict

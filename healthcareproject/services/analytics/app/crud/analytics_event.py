from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.analytics_event import AnalyticsEvent
from app.schemas.metrics import MetricsRead

_PATIENT_REGISTERED = "patient.registered"
_APPOINTMENT_BOOKED = "appointment.booked"
_APPOINTMENT_CANCELLED = "appointment.cancelled"
_VISIT_COMPLETED = "visit.completed"


def already_processed(db: Session, event_id: str) -> bool:
    return db.scalar(select(AnalyticsEvent).where(AnalyticsEvent.event_id == event_id)) is not None


def record(
    db: Session,
    *,
    event_id: str,
    event_type: str,
    actor: str | None,
    payload: dict,
) -> AnalyticsEvent | None:
    """Returns None (not an error) if event_id already exists — same
    unique-constraint-is-the-source-of-truth dedup as notification/audit."""
    event = AnalyticsEvent(
        id=uuid.uuid4(),
        event_id=event_id,
        event_type=event_type,
        actor=actor,
        payload=payload,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return event


def list_recent(db: Session, limit: int = 50) -> list[AnalyticsEvent]:
    return list(
        db.scalars(select(AnalyticsEvent).order_by(AnalyticsEvent.created_at.desc()).limit(limit))
    )


def _count(db: Session, event_type: str) -> int:
    return db.scalar(
        select(func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.event_type == event_type)
    ) or 0


def compute_metrics(db: Session) -> MetricsRead:
    """Derives the dashboard metrics from raw stored events rather than
    running counters — see AnalyticsEvent's docstring for why. Wait time
    is computed from visit.completed's own payload (started_at minus
    checked_in_at, both stamped by booking's visit lifecycle), not from
    anything analytics tracks independently.

    appointments_booked is a permanent historical count — it does NOT
    decrement when an appointment is later cancelled (cancelling doesn't
    undo the fact that it was booked). cancelled_appointments is the
    other half of that same funnel, exposed as a raw count alongside
    cancellation_rate (the ratio), not instead of it. upcoming_appointments
    is whatever's left once cancelled and completed are both accounted
    for — booked, confirmed, but not yet visited or cancelled — so the
    three counts always sum back to appointments_booked with nothing left
    implicit."""
    total_patients = _count(db, _PATIENT_REGISTERED)
    appointments_booked = _count(db, _APPOINTMENT_BOOKED)
    completed_visits = _count(db, _VISIT_COMPLETED)
    cancelled = _count(db, _APPOINTMENT_CANCELLED)
    cancellation_rate = (cancelled / appointments_booked) if appointments_booked else 0.0
    upcoming_appointments = appointments_booked - cancelled - completed_visits

    wait_seconds: list[float] = []
    visit_rows = db.scalars(
        select(AnalyticsEvent).where(AnalyticsEvent.event_type == _VISIT_COMPLETED)
    )
    for row in visit_rows:
        checked_in_at = datetime.fromisoformat(row.payload["checked_in_at"])
        started_at = datetime.fromisoformat(row.payload["started_at"])
        wait_seconds.append((started_at - checked_in_at).total_seconds())
    avg_wait_time_seconds = (sum(wait_seconds) / len(wait_seconds)) if wait_seconds else 0.0

    return MetricsRead(
        total_patients=total_patients,
        appointments_booked=appointments_booked,
        cancelled_appointments=cancelled,
        completed_visits=completed_visits,
        upcoming_appointments=upcoming_appointments,
        cancellation_rate=cancellation_rate,
        avg_wait_time_seconds=avg_wait_time_seconds,
    )

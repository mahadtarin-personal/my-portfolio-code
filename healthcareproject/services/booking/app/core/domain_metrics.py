from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.outbox_event import OutboxEvent


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def compute_outbox_metrics() -> dict[str, tuple[str, float]]:
    """Same outbox-lag shape as profiles (services/profiles/app/core/domain_metrics.py) —
    booking runs the identical outbox + relay pattern, so the two collectors
    stay independent per-service gauges (`job` label tells them apart in
    Prometheus/Grafana) rather than a shared lib function, since each reads
    its own service's DB session."""
    with SessionLocal() as db:
        unpublished = (
            db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
            )
            or 0
        )
        oldest = db.scalar(
            select(func.min(OutboxEvent.created_at)).where(OutboxEvent.published_at.is_(None))
        )

    age_seconds = (datetime.now(timezone.utc) - _as_utc(oldest)).total_seconds() if oldest else 0.0

    return {
        "smarthealth_outbox_unpublished_events": (
            "Outbox rows not yet published to Kafka",
            float(unpublished),
        ),
        "smarthealth_outbox_oldest_unpublished_age_seconds": (
            "Age in seconds of the oldest unpublished outbox row (0 if none)",
            age_seconds,
        ),
    }


def compute_appointment_funnel_rows() -> list[tuple[list[str], float]]:
    """One row per AppointmentStatus, real `status` label, so Grafana can
    stack the funnel (pending -> reserved -> payment_pending -> confirmed
    -> completed, with cancelled/failed as exits) with `sum by (status)`.
    Statuses with zero rows still get reported as 0 so a stacked panel
    doesn't silently drop a series."""
    with SessionLocal() as db:
        rows = dict(
            db.execute(
                select(Appointment.status, func.count()).group_by(Appointment.status)
            ).all()
        )

    return [([status.value], float(rows.get(status, 0))) for status in AppointmentStatus]

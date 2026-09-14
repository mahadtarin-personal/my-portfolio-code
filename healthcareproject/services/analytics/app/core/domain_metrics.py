from __future__ import annotations

from app.crud.analytics_event import compute_metrics
from app.db.session import SessionLocal


def compute_business_metrics() -> dict[str, tuple[str, float]]:
    """Re-exposes the same numbers /metrics already serves as JSON
    (see app/crud/analytics_event.py::compute_metrics) as Prometheus
    gauges, so Grafana can chart them over time instead of only ever
    seeing the current snapshot a human requests."""
    with SessionLocal() as db:
        metrics = compute_metrics(db)

    return {
        "smarthealth_total_patients": ("Total registered patients", float(metrics.total_patients)),
        "smarthealth_appointments_booked_total": (
            "Permanent historical count of appointments ever booked",
            float(metrics.appointments_booked),
        ),
        "smarthealth_appointments_cancelled_total": (
            "Permanent historical count of appointments ever cancelled",
            float(metrics.cancelled_appointments),
        ),
        "smarthealth_visits_completed_total": (
            "Permanent historical count of completed visits",
            float(metrics.completed_visits),
        ),
        "smarthealth_appointments_upcoming": (
            "Booked, confirmed, not yet visited or cancelled",
            float(metrics.upcoming_appointments),
        ),
        "smarthealth_cancellation_rate": (
            "cancelled_appointments / appointments_booked",
            metrics.cancellation_rate,
        ),
        "smarthealth_avg_wait_time_seconds": (
            "Average checked_in_at -> started_at across completed visits",
            metrics.avg_wait_time_seconds,
        ),
    }

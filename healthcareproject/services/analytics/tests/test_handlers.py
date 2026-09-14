import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from kafka_shared import EventEnvelope, Topic

from app import crud
from app.handlers import handle_event


def _envelope(event_type: Topic, *, actor: str | None = None, payload: dict | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
        actor=actor,
        payload=payload or {},
    )


def test_handle_event_records_an_event(db) -> None:
    envelope = _envelope(Topic.APPOINTMENT_BOOKED, actor="patient-1", payload={"appointment_id": "a1"})
    handle_event(envelope)

    rows = crud.analytics_event.list_recent(db)
    assert len(rows) == 1
    assert rows[0].event_id == envelope.event_id
    assert rows[0].event_type == "appointment.booked"
    assert rows[0].actor == "patient-1"


def test_handle_event_is_idempotent_on_replay(db) -> None:
    envelope = _envelope(Topic.APPOINTMENT_BOOKED, actor="patient-2")

    handle_event(envelope)
    handle_event(envelope)  # simulates Kafka redelivering the same event_id

    rows = crud.analytics_event.list_recent(db)
    assert len(rows) == 1


def test_metrics_counts_registrations_bookings_and_completions(db) -> None:
    handle_event(_envelope(Topic.PATIENT_REGISTERED))
    handle_event(_envelope(Topic.PATIENT_REGISTERED))
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED))
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED))
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED))
    handle_event(
        _envelope(
            Topic.VISIT_COMPLETED,
            payload={
                "checked_in_at": "2026-08-27T09:00:00+00:00",
                "started_at": "2026-08-27T09:10:00+00:00",
                "completed_at": "2026-08-27T09:30:00+00:00",
            },
        )
    )

    metrics = crud.analytics_event.compute_metrics(db)
    assert metrics.total_patients == 2
    assert metrics.appointments_booked == 3
    assert metrics.completed_visits == 1
    # 3 booked, 1 completed, 0 cancelled -> 2 still upcoming.
    assert metrics.upcoming_appointments == 2


def test_metrics_cancellation_rate(db) -> None:
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED))
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED))
    handle_event(_envelope(Topic.APPOINTMENT_CANCELLED))

    metrics = crud.analytics_event.compute_metrics(db)
    assert metrics.cancellation_rate == 0.5
    assert metrics.cancelled_appointments == 1
    # appointments_booked is a permanent historical count — cancelling
    # one does NOT decrement it back down.
    assert metrics.appointments_booked == 2
    assert metrics.upcoming_appointments == 1


def test_metrics_cancellation_rate_is_zero_with_no_bookings(db) -> None:
    metrics = crud.analytics_event.compute_metrics(db)
    assert metrics.cancellation_rate == 0.0
    assert metrics.cancelled_appointments == 0
    assert metrics.upcoming_appointments == 0


def test_metrics_booked_always_equals_cancelled_plus_completed_plus_upcoming(db) -> None:
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED))
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED))
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED))
    handle_event(_envelope(Topic.APPOINTMENT_CANCELLED))
    handle_event(
        _envelope(
            Topic.VISIT_COMPLETED,
            payload={
                "checked_in_at": "2026-08-27T09:00:00+00:00",
                "started_at": "2026-08-27T09:10:00+00:00",
                "completed_at": "2026-08-27T09:30:00+00:00",
            },
        )
    )

    metrics = crud.analytics_event.compute_metrics(db)
    assert (
        metrics.cancelled_appointments + metrics.completed_visits + metrics.upcoming_appointments
        == metrics.appointments_booked
    )


def test_metrics_avg_wait_time_averages_across_visits(db) -> None:
    checked_in = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)
    for minutes in (5, 15):
        started = checked_in + timedelta(minutes=minutes)
        handle_event(
            _envelope(
                Topic.VISIT_COMPLETED,
                payload={
                    "checked_in_at": checked_in.isoformat(),
                    "started_at": started.isoformat(),
                    "completed_at": (started + timedelta(minutes=20)).isoformat(),
                },
            )
        )

    metrics = crud.analytics_event.compute_metrics(db)
    assert metrics.avg_wait_time_seconds == (5 * 60 + 15 * 60) / 2


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint(client: TestClient, db) -> None:
    handle_event(_envelope(Topic.PATIENT_REGISTERED))
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.json()["total_patients"] == 1


def test_events_endpoint(client: TestClient, db) -> None:
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED, actor="patient-3"))
    response = client.get("/events")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["actor"] == "patient-3"

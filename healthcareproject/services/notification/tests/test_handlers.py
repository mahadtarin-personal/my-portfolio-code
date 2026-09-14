import uuid
from datetime import datetime, timezone

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


def test_handle_event_records_a_notification(db) -> None:
    envelope = _envelope(Topic.APPOINTMENT_BOOKED, actor="patient-1", payload={"appointment_id": "a1"})
    handle_event(envelope)

    rows = crud.notification.list_recent(db)
    assert len(rows) == 1
    assert rows[0].event_id == envelope.event_id
    assert rows[0].recipient == "patient-1"
    assert rows[0].message == "Your appointment is confirmed."
    assert rows[0].status.value == "sent"


def test_handle_event_falls_back_to_payload_patient_id_when_no_actor(db) -> None:
    envelope = _envelope(Topic.APPOINTMENT_CANCELLED, actor=None, payload={"patient_id": "patient-2"})
    handle_event(envelope)

    rows = crud.notification.list_recent(db)
    assert rows[0].recipient == "patient-2"


def test_handle_event_is_idempotent_on_replay(db) -> None:
    envelope = _envelope(Topic.APPOINTMENT_RESCHEDULED, actor="patient-3")

    handle_event(envelope)
    handle_event(envelope)  # simulates Kafka redelivering the same event_id

    rows = crud.notification.list_recent(db)
    assert len(rows) == 1


def test_unmapped_topic_gets_a_generic_message(db) -> None:
    envelope = _envelope(Topic.CLINICAL_RESULT_ADDED, actor="patient-4")
    handle_event(envelope)

    rows = crud.notification.list_recent(db)
    assert rows[0].message == "Update: clinical.result_added"


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_notifications_endpoint(client: TestClient, db) -> None:
    handle_event(_envelope(Topic.APPOINTMENT_BOOKED, actor="patient-5"))
    response = client.get("/notifications")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["recipient"] == "patient-5"

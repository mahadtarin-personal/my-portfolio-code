import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import crud
from app.models.calendar_sync_log import CalendarSyncAction


def test_list_calendar_sync_log(client: TestClient, db) -> None:
    appointment_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    crud.calendar_sync_log.record(
        db, appointment_id=appointment_id, provider_id=provider_id, action=CalendarSyncAction.SYNCED
    )
    db.commit()

    response = client.get("/calendar-sync-log")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["appointment_id"] == str(appointment_id)
    assert body[0]["action"] == "synced"


def test_list_calendar_sync_log_filters_by_appointment_id(client: TestClient, db) -> None:
    target = uuid.uuid4()
    other = uuid.uuid4()
    provider_id = uuid.uuid4()
    crud.calendar_sync_log.record(db, appointment_id=target, provider_id=provider_id, action=CalendarSyncAction.SYNCED)
    crud.calendar_sync_log.record(db, appointment_id=other, provider_id=provider_id, action=CalendarSyncAction.SYNCED)
    db.commit()

    response = client.get(f"/calendar-sync-log?appointment_id={target}")
    body = response.json()
    assert len(body) == 1
    assert body[0]["appointment_id"] == str(target)


def test_list_reminders(client: TestClient, db) -> None:
    appointment_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    crud.reminder_log.record(
        db,
        appointment_id=appointment_id,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=datetime.now(timezone.utc) + timedelta(days=1),
        appointment_status="confirmed",
    )
    db.commit()

    response = client.get("/reminders")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["appointment_id"] == str(appointment_id)
    assert body[0]["patient_id"] == str(patient_id)
    assert body[0]["status"] == "scheduled"


def test_list_reminders_filters_by_appointment_id(client: TestClient, db) -> None:
    target = uuid.uuid4()
    other = uuid.uuid4()
    patient_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    start_time = datetime.now(timezone.utc) + timedelta(days=1)
    crud.reminder_log.record(
        db,
        appointment_id=target,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=start_time,
        appointment_status="confirmed",
    )
    crud.reminder_log.record(
        db,
        appointment_id=other,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=start_time,
        appointment_status="confirmed",
    )
    db.commit()

    response = client.get(f"/reminders?appointment_id={target}")
    body = response.json()
    assert len(body) == 1
    assert body[0]["appointment_id"] == str(target)

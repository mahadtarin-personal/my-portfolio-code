import uuid

from fastapi.testclient import TestClient
from jwt_shared import Role

from app.models.appointment import Appointment, AppointmentStatus
from app.models.slot import Slot
from tests.conftest import auth_header


def _confirmed_appointment(db, slot: Slot) -> Appointment:
    appointment = Appointment(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        provider_id=slot.provider_id,
        slot_id=slot.id,
        status=AppointmentStatus.CONFIRMED,
    )
    db.add(appointment)
    db.commit()
    return appointment


def test_full_visit_lifecycle_marks_appointment_completed(
    client: TestClient, open_slot: Slot, db
) -> None:
    appointment = _confirmed_appointment(db, open_slot)
    front_desk_headers = auth_header("front-desk-1", Role.FRONT_DESK)
    provider_headers = auth_header(open_slot.provider_id, Role.PROVIDER)

    check_in = client.post(f"/appointments/{appointment.id}/check-in", headers=front_desk_headers)
    assert check_in.status_code == 201
    assert check_in.json()["status"] == "checked_in"

    start = client.post(f"/appointments/{appointment.id}/start", headers=provider_headers)
    assert start.status_code == 200
    assert start.json()["status"] == "in_progress"

    complete = client.post(f"/appointments/{appointment.id}/complete", headers=provider_headers)
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"

    # This is the fix: completing the visit should also complete the appointment.
    status_response = client.get(
        f"/appointments/{appointment.id}/status", headers=front_desk_headers
    )
    assert status_response.json()["status"] == "completed"


def test_start_visit_before_check_in_404s(client: TestClient, open_slot: Slot, db) -> None:
    appointment = _confirmed_appointment(db, open_slot)
    provider_headers = auth_header(open_slot.provider_id, Role.PROVIDER)
    response = client.post(f"/appointments/{appointment.id}/start", headers=provider_headers)
    assert response.status_code == 404


def test_check_in_twice_conflicts(client: TestClient, open_slot: Slot, db) -> None:
    appointment = _confirmed_appointment(db, open_slot)
    front_desk_headers = auth_header("front-desk-1", Role.FRONT_DESK)
    client.post(f"/appointments/{appointment.id}/check-in", headers=front_desk_headers)
    response = client.post(f"/appointments/{appointment.id}/check-in", headers=front_desk_headers)
    assert response.status_code == 409

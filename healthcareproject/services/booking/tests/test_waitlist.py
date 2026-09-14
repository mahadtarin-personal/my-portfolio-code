import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from jwt_shared import Role

from app.models.appointment import Appointment, AppointmentStatus
from app.models.slot import Slot, SlotStatus
from app.services.waitlist_promotion import PromotionAction, promote_next_waitlisted
from tests.conftest import auth_header


def _confirmed_appointment(db, slot: Slot, patient_id: uuid.UUID | None = None) -> Appointment:
    appointment = Appointment(
        id=uuid.uuid4(),
        patient_id=patient_id or uuid.uuid4(),
        provider_id=slot.provider_id,
        slot_id=slot.id,
        status=AppointmentStatus.CONFIRMED,
    )
    db.add(appointment)
    db.commit()
    return appointment


def test_joining_an_open_slot_is_rejected(client: TestClient, open_slot: Slot) -> None:
    headers = auth_header(uuid.uuid4(), Role.PATIENT)
    response = client.post("/waitlist", json={"slot_id": str(open_slot.id)}, headers=headers)
    assert response.status_code == 400


def test_joining_a_taken_slot_succeeds(client: TestClient, open_slot: Slot, db) -> None:
    _confirmed_appointment(db, open_slot)
    open_slot.status = SlotStatus.RESERVED
    db.commit()

    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    response = client.post("/waitlist", json={"slot_id": str(open_slot.id)}, headers=headers)
    assert response.status_code == 201
    assert response.json()["status"] == "waiting"


def test_joining_the_same_slot_twice_conflicts(client: TestClient, open_slot: Slot, db) -> None:
    _confirmed_appointment(db, open_slot)
    open_slot.status = SlotStatus.RESERVED
    db.commit()

    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    client.post("/waitlist", json={"slot_id": str(open_slot.id)}, headers=headers)
    response = client.post("/waitlist", json={"slot_id": str(open_slot.id)}, headers=headers)
    assert response.status_code == 409


def test_promote_next_waitlisted_no_existing_appointment_books_fresh(
    client: TestClient, open_slot: Slot, db
) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    open_slot.status = SlotStatus.RESERVED
    db.commit()
    client.post("/waitlist", json={"slot_id": str(open_slot.id)}, headers=headers)

    open_slot.status = SlotStatus.OPEN
    db.commit()
    result = promote_next_waitlisted(db, open_slot.provider_id, open_slot.id)
    db.commit()

    assert result is not None
    assert result.action == PromotionAction.FRESH_BOOKING
    assert result.patient_id == patient_id
    assert result.appointment.status == AppointmentStatus.PENDING
    assert result.appointment.slot_id == open_slot.id


def test_promote_next_waitlisted_with_existing_appointment_shifts_it(
    client: TestClient, open_slot: Slot, db
) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    open_slot.status = SlotStatus.RESERVED
    db.commit()
    client.post("/waitlist", json={"slot_id": str(open_slot.id)}, headers=headers)

    # The same patient already holds a confirmed appointment with this
    # provider, on a different slot.
    other_start = open_slot.start_time + timedelta(days=3)
    other_slot = Slot(
        id=uuid.uuid4(),
        provider_id=open_slot.provider_id,
        start_time=other_start,
        end_time=other_start + timedelta(minutes=20),
        status=SlotStatus.RESERVED,
    )
    db.add(other_slot)
    db.commit()
    existing_appointment = _confirmed_appointment(db, other_slot, patient_id=patient_id)

    open_slot.status = SlotStatus.OPEN
    db.commit()
    result = promote_next_waitlisted(db, open_slot.provider_id, open_slot.id)
    db.commit()

    assert result is not None
    assert result.action == PromotionAction.SHIFT_EXISTING
    assert result.appointment.id == existing_appointment.id


def test_promote_next_waitlisted_returns_none_when_nobody_waiting(
    open_slot: Slot, db
) -> None:
    result = promote_next_waitlisted(db, open_slot.provider_id, open_slot.id)
    assert result is None


def test_list_waitlist_by_patient_id(client: TestClient, open_slot: Slot, db) -> None:
    _confirmed_appointment(db, open_slot)
    open_slot.status = SlotStatus.RESERVED
    db.commit()

    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    client.post("/waitlist", json={"slot_id": str(open_slot.id)}, headers=headers)

    response = client.get("/waitlist", params={"patient_id": str(patient_id)}, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "waiting"


def test_list_waitlist_by_patient_id_rejects_other_patient(
    client: TestClient, open_slot: Slot, db
) -> None:
    patient_id = uuid.uuid4()
    other_headers = auth_header(uuid.uuid4(), Role.PATIENT)
    response = client.get("/waitlist", params={"patient_id": str(patient_id)}, headers=other_headers)
    assert response.status_code == 403


def test_list_waitlist_requires_slot_id_or_patient_id(client: TestClient) -> None:
    headers = auth_header(uuid.uuid4(), Role.PATIENT)
    response = client.get("/waitlist", headers=headers)
    assert response.status_code == 400

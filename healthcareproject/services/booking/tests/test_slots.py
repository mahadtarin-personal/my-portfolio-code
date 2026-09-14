import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jwt_shared import Role

from app.models.appointment import Appointment, AppointmentStatus
from app.models.slot import Slot, SlotStatus
from tests.conftest import auth_header


def test_list_open_slots_requires_auth(client: TestClient, open_slot: Slot) -> None:
    response = client.get("/slots")
    assert response.status_code == 401


def test_list_open_slots_returns_only_open(client: TestClient, open_slot: Slot, db) -> None:
    # Different start_time than open_slot — a provider can't have two slots
    # starting at the same instant (uq_slots_provider_start).
    blocked = Slot(
        id=uuid.uuid4(),
        provider_id=open_slot.provider_id,
        start_time=open_slot.start_time + timedelta(hours=1),
        end_time=open_slot.end_time + timedelta(hours=1),
        status=SlotStatus.BLOCKED,
    )
    db.add(blocked)
    db.commit()

    headers = auth_header("patient-1", Role.PATIENT)
    response = client.get("/slots", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(open_slot.id)


def test_list_open_slots_filters_by_provider(client: TestClient, open_slot: Slot) -> None:
    headers = auth_header("patient-1", Role.PATIENT)
    response = client.get("/slots", params={"provider_id": str(uuid.uuid4())}, headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_open_slots_excludes_a_past_slot_nobody_ever_booked(
    client: TestClient, open_slot: Slot, db
) -> None:
    # status=OPEN alone doesn't mean bookable — once start_time passes with
    # nobody booking it, nothing ever transitions the row out of OPEN. A
    # stale never-booked slot from before "now" must not show up as
    # available, regardless of provider filter.
    stale = Slot(
        id=uuid.uuid4(),
        provider_id=open_slot.provider_id,
        start_time=datetime.now(timezone.utc) - timedelta(days=1),
        end_time=datetime.now(timezone.utc) - timedelta(days=1) + timedelta(minutes=20),
        status=SlotStatus.OPEN,
    )
    db.add(stale)
    db.commit()

    headers = auth_header("patient-1", Role.PATIENT)

    unfiltered = client.get("/slots", headers=headers)
    assert unfiltered.status_code == 200
    assert [s["id"] for s in unfiltered.json()] == [str(open_slot.id)]

    filtered = client.get("/slots", params={"provider_id": str(open_slot.provider_id)}, headers=headers)
    assert filtered.status_code == 200
    assert [s["id"] for s in filtered.json()] == [str(open_slot.id)]


# ---- Slot.appointment relationship (uselist=False + primaryjoin) ----


def test_slot_appointment_ignores_a_stale_cancelled_row_on_the_same_slot(db) -> None:
    """A slot can legitimately have more than one appointment row over its
    history (uq_appointments_slot_id_active only enforces uniqueness among
    ACTIVE statuses) -- a cancelled booking followed by a fresh one on the
    same slot is completely normal. Slot.appointment must resolve to the
    current active row, not whichever one a plain FK match happens to
    return first. Hit live: without the primaryjoin filter, this silently
    returned the stale CANCELLED row instead (SAWarning, no error) --
    exactly the kind of bug that would break reserve_slot's retry
    disambiguation (app/activities/booking.py), which compares
    slot.appointment.id against the appointment actually being reserved."""
    provider_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = Slot(
        id=uuid.uuid4(), provider_id=provider_id, start_time=start,
        end_time=start + timedelta(minutes=20), status=SlotStatus.OPEN,
    )
    db.add(slot)
    db.commit()

    cancelled = Appointment(
        id=uuid.uuid4(), patient_id=uuid.uuid4(), provider_id=provider_id,
        slot_id=slot.id, status=AppointmentStatus.CANCELLED,
    )
    db.add(cancelled)
    db.commit()

    active = Appointment(
        id=uuid.uuid4(), patient_id=uuid.uuid4(), provider_id=provider_id,
        slot_id=slot.id, status=AppointmentStatus.CONFIRMED,
    )
    db.add(active)
    db.commit()

    db.expire_all()
    resolved = slot.appointment
    assert resolved is not None
    assert resolved.id == active.id


# ---- Reconcile trigger ----


def test_reconcile_uses_a_deterministic_workflow_id(client: TestClient, fake_temporal_client) -> None:
    """No uuid4() suffix -- one provider always maps to the same workflow
    id, so Temporal itself refuses a second concurrent reconcile for the
    same provider rather than piling up redundant runs."""
    provider_id = uuid.uuid4()
    response = client.post("/slots/reconcile", params={"provider_id": str(provider_id)})
    assert response.status_code == 202
    assert len(fake_temporal_client.started) == 1
    _, kwargs = fake_temporal_client.started[0]
    assert kwargs["id"] == f"reconcile-{provider_id}"


def test_reconcile_tolerates_one_already_running_for_the_same_provider(
    client: TestClient, fake_temporal_client
) -> None:
    """A duplicate trigger while one's still in flight raises
    WorkflowAlreadyStartedError -- not a real error, so the endpoint must
    still return success rather than 500ing on the service-to-service
    caller (profiles)."""
    fake_temporal_client.raise_already_started = True
    response = client.post("/slots/reconcile", params={"provider_id": str(uuid.uuid4())})
    assert response.status_code == 202
    assert response.json() == {"status": "triggered"}

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jwt_shared import Role

from app import crud
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.calendar_sync_log import CalendarSyncAction
from app.models.slot import Slot, SlotStatus
from tests.conftest import FakeTemporalClient, auth_header


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


def _make_reserved_slot(db) -> Slot:
    provider_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = crud.slot.create(db, provider_id=provider_id, start_time=start, end_time=start + timedelta(minutes=20))
    slot.status = SlotStatus.RESERVED
    db.commit()
    return slot


def _book(client: TestClient, *, patient_id, provider_id, slot_id, idempotency_key=None, headers):
    return client.post(
        "/appointments",
        json={
            "patient_id": str(patient_id),
            "provider_id": str(provider_id),
            "slot_id": str(slot_id),
        },
        headers={**headers, "Idempotency-Key": idempotency_key or str(uuid.uuid4())},
    )


def test_patient_can_start_booking_own_slot(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    response = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=headers,
    )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"


def test_create_appointment_is_rate_limited_after_20_per_minute(client: TestClient, open_slot: Slot) -> None:
    # app.state.limiter's storage is shared across every test in this
    # process (one app instance, imported once at module level) — reset
    # before AND after, same reasoning as profiles' equivalent test.
    # Reuses the SAME idempotency key for every call (an idempotent
    # replay, not a fresh booking each time) so this doesn't need 21
    # distinct open slots.
    app.state.limiter.reset()
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    key = str(uuid.uuid4())
    try:
        for _ in range(20):
            response = _book(
                client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
                idempotency_key=key, headers=headers,
            )
            assert response.status_code == 202

        throttled = _book(
            client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
            idempotency_key=key, headers=headers,
        )
        assert throttled.status_code == 429
    finally:
        app.state.limiter.reset()


def test_booking_requires_idempotency_key(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    response = client.post(
        "/appointments",
        json={
            "patient_id": str(patient_id),
            "provider_id": str(open_slot.provider_id),
            "slot_id": str(open_slot.id),
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_replaying_the_same_idempotency_key_returns_the_same_appointment(
    client: TestClient, open_slot: Slot
) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    key = str(uuid.uuid4())

    first = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        idempotency_key=key, headers=headers,
    )
    second = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        idempotency_key=key, headers=headers,
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]


def test_patient_cannot_book_on_behalf_of_another_patient(
    client: TestClient, open_slot: Slot
) -> None:
    headers = auth_header(uuid.uuid4(), Role.PATIENT)
    response = _book(
        client, patient_id=uuid.uuid4(), provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=headers,
    )
    assert response.status_code == 403


def test_double_booking_the_same_slot_conflicts(client: TestClient, open_slot: Slot) -> None:
    first_patient = uuid.uuid4()
    _book(
        client, patient_id=first_patient, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=auth_header(first_patient, Role.PATIENT),
    )

    second_patient = uuid.uuid4()
    response = _book(
        client, patient_id=second_patient, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=auth_header(second_patient, Role.PATIENT),
    )
    assert response.status_code == 409


def test_patient_can_read_own_appointment_status(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    created = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=headers,
    ).json()

    response = client.get(f"/appointments/{created['id']}/status", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_patient_can_list_their_own_appointments(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    created = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=headers,
    ).json()

    response = client.get("/appointments", params={"patient_id": str(patient_id)}, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == created["id"]


def test_patient_cannot_list_another_patients_appointments(client: TestClient) -> None:
    patient_id = uuid.uuid4()
    other_headers = auth_header(uuid.uuid4(), Role.PATIENT)
    response = client.get("/appointments", params={"patient_id": str(patient_id)}, headers=other_headers)
    assert response.status_code == 403


def test_provider_can_list_their_own_appointments(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    created = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=auth_header(patient_id, Role.PATIENT),
    ).json()

    provider_headers = auth_header(open_slot.provider_id, Role.PROVIDER)
    response = client.get(
        "/appointments", params={"provider_id": str(open_slot.provider_id)}, headers=provider_headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == created["id"]


def test_front_desk_can_list_any_providers_appointments(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=auth_header(patient_id, Role.PATIENT),
    )

    front_desk_headers = auth_header("front-desk-1", Role.FRONT_DESK)
    response = client.get(
        "/appointments", params={"provider_id": str(open_slot.provider_id)}, headers=front_desk_headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_other_provider_cannot_list_appointments(client: TestClient, open_slot: Slot) -> None:
    other_provider_headers = auth_header(uuid.uuid4(), Role.PROVIDER)
    response = client.get(
        "/appointments", params={"provider_id": str(open_slot.provider_id)}, headers=other_provider_headers
    )
    assert response.status_code == 403


def test_list_appointments_requires_patient_id_or_provider_id(client: TestClient) -> None:
    headers = auth_header(uuid.uuid4(), Role.PATIENT)
    response = client.get("/appointments", headers=headers)
    assert response.status_code == 400


def test_other_patient_cannot_read_appointment_status(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    created = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=auth_header(patient_id, Role.PATIENT),
    ).json()

    other_headers = auth_header(uuid.uuid4(), Role.PATIENT)
    response = client.get(f"/appointments/{created['id']}/status", headers=other_headers)
    assert response.status_code == 403


def test_cancel_pending_appointment(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    created = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=headers,
    ).json()

    cancel_response = client.patch(
        f"/appointments/{created['id']}", json={"status": "cancelled"}, headers=headers
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    # The slot was never actually reserved (no worker running the saga in
    # this test process — see test_booking_saga.py for that), so it's still
    # open; cancelling a PENDING appointment is still a valid, harmless
    # transition regardless.
    slots_response = client.get("/slots", headers=headers)
    assert any(s["id"] == str(open_slot.id) for s in slots_response.json())


def test_cancel_publishes_appointment_cancelled_event(
    client: TestClient, open_slot: Slot, monkeypatch
) -> None:
    from kafka_shared import Topic

    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    created = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=headers,
    ).json()

    calls = []
    monkeypatch.setattr(
        "app.routers.appointments.publish",
        lambda db, event_type, payload, *, actor=None: calls.append((event_type, payload, actor)),
    )

    client.patch(f"/appointments/{created['id']}", json={"status": "cancelled"}, headers=headers)

    assert len(calls) == 1
    event_type, payload, actor = calls[0]
    assert event_type == Topic.APPOINTMENT_CANCELLED
    assert payload == {
        "appointment_id": created["id"],
        "patient_id": str(patient_id),
        "provider_id": str(open_slot.provider_id),
        "slot_id": str(open_slot.id),
    }
    assert actor == str(patient_id)


def test_cancel_marks_a_scheduled_reminder_as_skipped(client: TestClient, db) -> None:
    from app.models.reminder_log import ReminderLog, ReminderStatus

    slot = _make_reserved_slot(db)
    holder = _confirmed_appointment(db, slot)
    crud.reminder_log.record(
        db,
        appointment_id=holder.id,
        patient_id=holder.patient_id,
        provider_id=holder.provider_id,
        appointment_start_time=slot.start_time,
        appointment_status="confirmed",
    )
    db.commit()

    headers = auth_header(holder.patient_id, Role.PATIENT)
    response = client.patch(f"/appointments/{holder.id}", json={"status": "cancelled"}, headers=headers)
    assert response.status_code == 200

    reminder = db.query(ReminderLog).filter_by(appointment_id=holder.id).one()
    assert reminder.status == ReminderStatus.SKIPPED
    assert reminder.appointment_status == "cancelled"


def test_cancel_enqueues_a_calendar_revert(client: TestClient, db, monkeypatch) -> None:
    slot = _make_reserved_slot(db)
    holder = _confirmed_appointment(db, slot)
    crud.calendar_sync_log.record(
        db, appointment_id=holder.id, provider_id=holder.provider_id, action=CalendarSyncAction.SYNCED
    )
    db.commit()

    calls = []
    monkeypatch.setattr(
        "app.routers.appointments.sync_calendar_task.delay",
        lambda appointment_id, provider_id, action: calls.append((appointment_id, provider_id, action)),
    )

    headers = auth_header(holder.patient_id, Role.PATIENT)
    client.patch(f"/appointments/{holder.id}", json={"status": "cancelled"}, headers=headers)

    assert calls == [(str(holder.id), str(holder.provider_id), "reverted")]


def test_cancel_still_succeeds_if_the_calendar_revert_fails_to_enqueue(client: TestClient, db, monkeypatch) -> None:
    # Hit live: sync_calendar_task.delay() itself raised (broker briefly
    # unreachable) and the cancellation response 500'd even though the
    # cancellation had already committed. The cancel endpoint must never
    # let this fire-and-forget enqueue fail the request.
    slot = _make_reserved_slot(db)
    holder = _confirmed_appointment(db, slot)

    def _boom(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr("app.routers.appointments.sync_calendar_task.delay", _boom)

    headers = auth_header(holder.patient_id, Role.PATIENT)
    response = client.patch(f"/appointments/{holder.id}", json={"status": "cancelled"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_patch_only_accepts_cancelled_status(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    created = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=headers,
    ).json()

    response = client.patch(
        f"/appointments/{created['id']}", json={"status": "completed"}, headers=headers
    )
    assert response.status_code == 400


def test_cannot_cancel_an_already_cancelled_appointment(client: TestClient, open_slot: Slot) -> None:
    patient_id = uuid.uuid4()
    headers = auth_header(patient_id, Role.PATIENT)
    created = _book(
        client, patient_id=patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id,
        headers=headers,
    ).json()

    first = client.patch(
        f"/appointments/{created['id']}", json={"status": "cancelled"}, headers=headers
    )
    assert first.status_code == 200

    second = client.patch(
        f"/appointments/{created['id']}", json={"status": "cancelled"}, headers=headers
    )
    assert second.status_code == 409


def test_cannot_cancel_a_completed_appointment(client: TestClient, db) -> None:
    holder = _confirmed_appointment(db, _make_reserved_slot(db))
    holder.status = AppointmentStatus.COMPLETED
    db.commit()

    headers = auth_header(holder.patient_id, Role.PATIENT)
    response = client.patch(
        f"/appointments/{holder.id}", json={"status": "cancelled"}, headers=headers
    )
    assert response.status_code == 409


def test_cancelling_a_terminal_appointment_does_not_touch_its_slot(client: TestClient, db) -> None:
    # Regression guard: re-cancelling an already-cancelled appointment must
    # not force its slot back to OPEN — that slot may since have been
    # rebooked by someone else entirely, and forcing it open would corrupt
    # that other, unrelated booking.
    slot = _make_reserved_slot(db)
    holder = _confirmed_appointment(db, slot)
    holder.status = AppointmentStatus.CANCELLED
    db.commit()

    headers = auth_header(holder.patient_id, Role.PATIENT)
    response = client.patch(
        f"/appointments/{holder.id}", json={"status": "cancelled"}, headers=headers
    )
    assert response.status_code == 409

    refreshed_slot = db.get(Slot, slot.id)
    assert refreshed_slot.status == SlotStatus.RESERVED  # untouched, still "held" by whoever has it now


# ---- Waitlist promotion on cancel ----


def test_cancel_promotes_waitlisted_patient_with_no_existing_appointment(
    client: TestClient, open_slot: Slot, db, fake_temporal_client: FakeTemporalClient
) -> None:
    holder = _confirmed_appointment(db, open_slot)
    open_slot.status = SlotStatus.RESERVED
    db.commit()

    waiting_patient_id = uuid.uuid4()
    crud.waitlist.join(
        db, patient_id=waiting_patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id
    )
    db.commit()

    holder_headers = auth_header(holder.patient_id, Role.PATIENT)
    response = client.patch(
        f"/appointments/{holder.id}", json={"status": "cancelled"}, headers=holder_headers
    )
    assert response.status_code == 200

    assert len(fake_temporal_client.started) == 1
    started_args, started_kwargs = fake_temporal_client.started[0]
    assert started_args[0].__qualname__ == "BookingSagaWorkflow.run"
    # Deterministic on the promoted appointment's own (freshly-minted) id
    # -- no uuid4() suffix -- so a duplicate promotion attempt can't start
    # a second workflow for the same event.
    promoted = crud.appointment.list_for_patient(db, waiting_patient_id)[0]
    assert started_kwargs["id"] == f"booking-{promoted.id}"


def test_cancel_promotes_waitlisted_patient_by_shifting_existing_appointment(
    client: TestClient, open_slot: Slot, db, fake_temporal_client: FakeTemporalClient
) -> None:
    holder = _confirmed_appointment(db, open_slot)
    open_slot.status = SlotStatus.RESERVED
    db.commit()

    waiting_patient_id = uuid.uuid4()
    # The waiting patient already holds a confirmed appointment with the
    # same provider, on a different slot — promotion should shift it.
    other_start = open_slot.start_time + timedelta(days=5)
    other_slot = Slot(
        id=uuid.uuid4(),
        provider_id=open_slot.provider_id,
        start_time=other_start,
        end_time=other_start + timedelta(minutes=20),
        status=SlotStatus.RESERVED,
    )
    db.add(other_slot)
    db.commit()
    existing_appointment = _confirmed_appointment(db, other_slot, patient_id=waiting_patient_id)

    crud.waitlist.join(
        db, patient_id=waiting_patient_id, provider_id=open_slot.provider_id, slot_id=open_slot.id
    )
    db.commit()

    holder_headers = auth_header(holder.patient_id, Role.PATIENT)
    response = client.patch(
        f"/appointments/{holder.id}", json={"status": "cancelled"}, headers=holder_headers
    )
    assert response.status_code == 200
    assert len(fake_temporal_client.started) == 1
    started_args, started_kwargs = fake_temporal_client.started[0]
    assert started_args[0].__qualname__ == "RescheduleAppointmentWorkflow.run"
    # Deterministic on (the appointment being shifted, its target slot) --
    # no uuid4() suffix.
    assert started_kwargs["id"] == f"reschedule-{existing_appointment.id}-to-{open_slot.id}"


# ---- 30-minute cancel/reschedule buffer ----


def _confirmed_appointment_starting_soon(db, minutes_from_now: int) -> tuple[Appointment, Slot]:
    provider_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    slot = crud.slot.create(db, provider_id=provider_id, start_time=start, end_time=start + timedelta(minutes=20))
    slot.status = SlotStatus.RESERVED
    db.commit()
    appointment = _confirmed_appointment(db, slot)
    return appointment, slot


def test_patient_cannot_cancel_within_30_minutes_of_start(client: TestClient, db) -> None:
    appointment, _ = _confirmed_appointment_starting_soon(db, minutes_from_now=10)
    headers = auth_header(appointment.patient_id, Role.PATIENT)
    response = client.patch(
        f"/appointments/{appointment.id}", json={"status": "cancelled"}, headers=headers
    )
    assert response.status_code == 409


def test_front_desk_can_cancel_within_30_minutes_of_start(client: TestClient, db) -> None:
    appointment, _ = _confirmed_appointment_starting_soon(db, minutes_from_now=10)
    headers = auth_header("front-desk-1", Role.FRONT_DESK)
    response = client.patch(
        f"/appointments/{appointment.id}", json={"status": "cancelled"}, headers=headers
    )
    assert response.status_code == 200


# ---- Reschedule endpoint ----


def test_reschedule_starts_workflow_and_returns_202(
    client: TestClient, db, fake_temporal_client: FakeTemporalClient
) -> None:
    appointment, old_slot = _confirmed_appointment_starting_soon(db, minutes_from_now=120)
    new_start = old_slot.start_time + timedelta(hours=2)
    new_slot = crud.slot.create(
        db, provider_id=old_slot.provider_id, start_time=new_start, end_time=new_start + timedelta(minutes=20)
    )
    db.commit()

    headers = auth_header(appointment.patient_id, Role.PATIENT)
    response = client.post(
        f"/appointments/{appointment.id}/reschedule",
        json={"new_slot_id": str(new_slot.id)},
        headers=headers,
    )
    assert response.status_code == 202
    assert len(fake_temporal_client.started) == 1
    _, started_kwargs = fake_temporal_client.started[0]
    # Deterministic on (the appointment, its target slot) -- no uuid4()
    # suffix -- so a retried reschedule request can't start a second,
    # concurrent workflow for the same move.
    assert started_kwargs["id"] == f"reschedule-{appointment.id}-to-{new_slot.id}"


def test_reschedule_workflow_id_is_the_same_across_a_retried_request(
    client: TestClient, db, fake_temporal_client: FakeTemporalClient
) -> None:
    """The actual property being fixed: retrying the identical reschedule
    request must produce the identical workflow id both times, not a
    fresh random one -- that's what lets Temporal itself refuse a
    concurrent duplicate rather than silently starting two workflows for
    one logical move."""
    appointment, old_slot = _confirmed_appointment_starting_soon(db, minutes_from_now=120)
    new_start = old_slot.start_time + timedelta(hours=2)
    new_slot = crud.slot.create(
        db, provider_id=old_slot.provider_id, start_time=new_start, end_time=new_start + timedelta(minutes=20)
    )
    db.commit()

    headers = auth_header(appointment.patient_id, Role.PATIENT)
    for _ in range(2):
        response = client.post(
            f"/appointments/{appointment.id}/reschedule",
            json={"new_slot_id": str(new_slot.id)},
            headers=headers,
        )
        assert response.status_code == 202

    assert len(fake_temporal_client.started) == 2
    first_id = fake_temporal_client.started[0][1]["id"]
    second_id = fake_temporal_client.started[1][1]["id"]
    assert first_id == second_id


def test_patient_cannot_reschedule_within_30_minutes_of_start(client: TestClient, db) -> None:
    appointment, old_slot = _confirmed_appointment_starting_soon(db, minutes_from_now=10)
    new_start = old_slot.start_time + timedelta(hours=2)
    new_slot = crud.slot.create(
        db, provider_id=old_slot.provider_id, start_time=new_start, end_time=new_start + timedelta(minutes=20)
    )
    db.commit()

    headers = auth_header(appointment.patient_id, Role.PATIENT)
    response = client.post(
        f"/appointments/{appointment.id}/reschedule",
        json={"new_slot_id": str(new_slot.id)},
        headers=headers,
    )
    assert response.status_code == 409

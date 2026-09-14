import uuid
from datetime import datetime, timedelta, timezone

from kafka_shared import Topic

from app import crud
from app.activities.reminder import SendReminderInput, send_reminder
from app.models.appointment import Appointment, AppointmentStatus
from app.models.outbox_event import OutboxEvent
from app.models.reminder_log import ReminderLog, ReminderStatus


def _make_confirmed_appointment(db, *, status: AppointmentStatus = AppointmentStatus.CONFIRMED) -> Appointment:
    provider_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = crud.slot.create(db, provider_id=provider_id, start_time=start, end_time=start + timedelta(minutes=20))
    appointment = Appointment(
        id=uuid.uuid4(),
        patient_id=patient_id,
        provider_id=provider_id,
        slot_id=slot.id,
        status=status,
    )
    db.add(appointment)
    db.commit()
    return appointment


def _schedule(db, appointment: Appointment) -> None:
    """Simulates what confirm_appointment does at booking-confirm time —
    the SCHEDULED row send_reminder later transitions."""
    crud.reminder_log.record(
        db,
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        provider_id=appointment.provider_id,
        appointment_start_time=appointment.slot.start_time,
        appointment_status="confirmed",
    )
    db.commit()


def _fire(appointment: Appointment, *, scheduled_for: datetime | None = None) -> None:
    """Calls send_reminder the way ReminderWorkflow does once its durable
    sleep wakes up — with the start time it was scheduled against.
    Defaults to the appointment's actual current slot time (the non-stale
    case); pass an explicit scheduled_for to simulate a workflow left over
    from before a reschedule. Called directly as a plain function — the
    same shortcut the old Celery version's eager-mode .delay() gave this
    test suite, since @activity.defn doesn't wrap execution the way
    Celery's @task does, and this activity makes no Temporal-context calls
    of its own (no activity.info()/heartbeat()) that would require a real
    worker to run under."""
    scheduled_for = scheduled_for or appointment.slot.start_time
    send_reminder(
        SendReminderInput(
            appointment_id=str(appointment.id),
            patient_id=str(appointment.patient_id),
            provider_id=str(appointment.provider_id),
            scheduled_for_start_time=scheduled_for.isoformat(),
        )
    )


def test_record_creates_a_scheduled_row(db) -> None:
    appointment = _make_confirmed_appointment(db)

    row = crud.reminder_log.record(
        db,
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        provider_id=appointment.provider_id,
        appointment_start_time=appointment.slot.start_time,
        appointment_status="confirmed",
    )

    assert row is not None
    assert row.status == ReminderStatus.SCHEDULED
    assert row.appointment_start_time == appointment.slot.start_time


def test_record_returns_none_on_duplicate_appointment(db) -> None:
    appointment_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    start_time = datetime.now(timezone.utc) + timedelta(days=1)

    first = crud.reminder_log.record(
        db,
        appointment_id=appointment_id,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=start_time,
        appointment_status="confirmed",
    )
    db.commit()
    assert first is not None

    second = crud.reminder_log.record(
        db,
        appointment_id=appointment_id,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=start_time,
        appointment_status="confirmed",
    )
    assert second is None


def test_mark_outcome_transitions_scheduled_to_sent(db) -> None:
    appointment_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    start_time = datetime.now(timezone.utc) + timedelta(days=1)
    crud.reminder_log.record(
        db,
        appointment_id=appointment_id,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=start_time,
        appointment_status="confirmed",
    )
    db.commit()

    row = crud.reminder_log.mark_outcome(
        db, appointment_id=appointment_id, status=ReminderStatus.SENT, appointment_status="confirmed"
    )

    assert row is not None
    assert row.status == ReminderStatus.SENT
    assert row.updated_at is not None


def test_mark_outcome_is_a_noop_if_not_currently_scheduled(db) -> None:
    appointment_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    start_time = datetime.now(timezone.utc) + timedelta(days=1)
    crud.reminder_log.record(
        db,
        appointment_id=appointment_id,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=start_time,
        appointment_status="confirmed",
    )
    db.commit()
    crud.reminder_log.mark_outcome(
        db, appointment_id=appointment_id, status=ReminderStatus.SENT, appointment_status="confirmed"
    )
    db.commit()

    # Retry-safety: a second transition attempt (e.g. Celery redelivery)
    # finds the row already past SCHEDULED and no-ops.
    replay = crud.reminder_log.mark_outcome(
        db, appointment_id=appointment_id, status=ReminderStatus.SENT, appointment_status="confirmed"
    )
    assert replay is None


def test_reschedule_moves_a_scheduled_row_to_rescheduled_with_the_new_time(db) -> None:
    appointment_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    old_start = datetime.now(timezone.utc) + timedelta(days=1)
    new_start = old_start + timedelta(hours=2)
    crud.reminder_log.record(
        db,
        appointment_id=appointment_id,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=old_start,
        appointment_status="confirmed",
    )
    db.commit()

    row = crud.reminder_log.reschedule(db, appointment_id=appointment_id, appointment_start_time=new_start)

    assert row is not None
    assert row.status == ReminderStatus.RESCHEDULED
    # SQLite (tests) returns naive datetimes; Postgres returns aware ones
    # — both semantically UTC, normalize before comparing.
    assert row.appointment_start_time.replace(tzinfo=None) == new_start.replace(tzinfo=None)


def test_reschedule_returns_none_if_no_reminder_was_ever_scheduled(db) -> None:
    row = crud.reminder_log.reschedule(
        db, appointment_id=uuid.uuid4(), appointment_start_time=datetime.now(timezone.utc)
    )
    assert row is None


def test_mark_outcome_transitions_rescheduled_to_sent(db) -> None:
    appointment_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    old_start = datetime.now(timezone.utc) + timedelta(days=1)
    new_start = old_start + timedelta(hours=2)
    crud.reminder_log.record(
        db,
        appointment_id=appointment_id,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=old_start,
        appointment_status="confirmed",
    )
    crud.reminder_log.reschedule(db, appointment_id=appointment_id, appointment_start_time=new_start)
    db.commit()

    row = crud.reminder_log.mark_outcome(
        db, appointment_id=appointment_id, status=ReminderStatus.SENT, appointment_status="confirmed"
    )
    assert row is not None
    assert row.status == ReminderStatus.SENT


def test_send_reminder_transitions_scheduled_row_to_sent_and_publishes(db) -> None:
    appointment = _make_confirmed_appointment(db)
    _schedule(db, appointment)

    _fire(appointment)

    log_row = db.query(ReminderLog).filter_by(appointment_id=appointment.id).one()
    assert log_row.status == ReminderStatus.SENT
    assert log_row.appointment_status == "confirmed"
    assert log_row.patient_id == appointment.patient_id
    assert log_row.provider_id == appointment.provider_id

    outbox_row = db.query(OutboxEvent).filter_by(topic=Topic.REMINDER_SCHEDULED.value).one()
    assert outbox_row.payload == {
        "appointment_id": str(appointment.id),
        "patient_id": str(appointment.patient_id),
        "provider_id": str(appointment.provider_id),
    }


def test_send_reminder_is_idempotent_on_replay(db) -> None:
    appointment = _make_confirmed_appointment(db)
    _schedule(db, appointment)

    _fire(appointment)
    _fire(appointment)

    rows = db.query(ReminderLog).filter_by(appointment_id=appointment.id).all()
    assert len(rows) == 1
    assert rows[0].status == ReminderStatus.SENT
    assert db.query(OutboxEvent).filter_by(topic=Topic.REMINDER_SCHEDULED.value).count() == 1


def test_send_reminder_transitions_to_skipped_for_a_cancelled_appointment(db) -> None:
    appointment = _make_confirmed_appointment(db)
    _schedule(db, appointment)
    appointment.status = AppointmentStatus.CANCELLED
    db.commit()

    _fire(appointment)

    log_row = db.query(ReminderLog).filter_by(appointment_id=appointment.id).one()
    assert log_row.status == ReminderStatus.SKIPPED
    assert log_row.appointment_status == "cancelled"
    assert db.query(OutboxEvent).filter_by(topic=Topic.REMINDER_SCHEDULED.value).first() is None


def test_send_reminder_noops_if_never_scheduled(db) -> None:
    appointment = _make_confirmed_appointment(db)

    # No prior _schedule() call — shouldn't happen via the real flow
    # (confirm_appointment always records SCHEDULED first), but the task
    # must not crash or fabricate a row if it somehow does.
    _fire(appointment)

    assert db.query(ReminderLog).filter_by(appointment_id=appointment.id).first() is None


def test_send_reminder_is_stale_after_a_reschedule_and_does_not_touch_the_row(db) -> None:
    appointment = _make_confirmed_appointment(db)
    _schedule(db, appointment)
    old_start = appointment.slot.start_time
    new_start = old_start + timedelta(hours=2)
    # Actually move the appointment's slot (not just the reminder row) —
    # otherwise appointment.slot.start_time would still equal old_start
    # and the "stale" call below wouldn't genuinely be stale.
    new_slot = crud.slot.create(
        db, provider_id=appointment.provider_id, start_time=new_start, end_time=new_start + timedelta(minutes=20)
    )
    appointment.slot_id = new_slot.id
    crud.reminder_log.reschedule(db, appointment_id=appointment.id, appointment_start_time=new_start)
    db.commit()
    db.refresh(appointment)

    # Simulates the ORIGINAL task (scheduled before the reschedule) still
    # firing at the OLD eta — it must back off, not resolve the row.
    _fire(appointment, scheduled_for=old_start)

    log_row = db.query(ReminderLog).filter_by(appointment_id=appointment.id).one()
    assert log_row.status == ReminderStatus.RESCHEDULED  # untouched by the stale task
    assert db.query(OutboxEvent).filter_by(topic=Topic.REMINDER_SCHEDULED.value).first() is None


def test_send_reminder_resolves_a_rescheduled_row_when_the_time_matches(db) -> None:
    appointment = _make_confirmed_appointment(db)
    _schedule(db, appointment)
    new_start = appointment.slot.start_time + timedelta(hours=2)
    # Simulate the actual reschedule: appointment's slot moves, and the
    # reminder row is transitioned to RESCHEDULED for the new time.
    new_slot = crud.slot.create(
        db, provider_id=appointment.provider_id, start_time=new_start, end_time=new_start + timedelta(minutes=20)
    )
    appointment.slot_id = new_slot.id
    crud.reminder_log.reschedule(db, appointment_id=appointment.id, appointment_start_time=new_start)
    db.commit()
    db.refresh(appointment)

    _fire(appointment, scheduled_for=new_start)

    log_row = db.query(ReminderLog).filter_by(appointment_id=appointment.id).one()
    assert log_row.status == ReminderStatus.SENT
    assert db.query(OutboxEvent).filter_by(topic=Topic.REMINDER_SCHEDULED.value).count() == 1

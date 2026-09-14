import uuid
from datetime import datetime, timedelta, timezone

from app import crud
from app.core.config import get_settings
from app.models.appointment import Appointment, AppointmentStatus
from app.models.calendar_sync_log import CalendarSyncAction, CalendarSyncLog
from app.tasks.calendar_sync import sync_calendar_task


def _make_confirmed_appointment(db) -> Appointment:
    provider_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = crud.slot.create(db, provider_id=provider_id, start_time=start, end_time=start + timedelta(minutes=20))
    appointment = Appointment(
        id=uuid.uuid4(),
        patient_id=patient_id,
        provider_id=provider_id,
        slot_id=slot.id,
        status=AppointmentStatus.CONFIRMED,
    )
    db.add(appointment)
    db.commit()
    return appointment


def test_record_returns_none_on_duplicate_appointment_action_pair(db) -> None:
    appointment_id = uuid.uuid4()
    provider_id = uuid.uuid4()

    first = crud.calendar_sync_log.record(
        db, appointment_id=appointment_id, provider_id=provider_id, action=CalendarSyncAction.SYNCED
    )
    db.commit()
    assert first is not None

    second = crud.calendar_sync_log.record(
        db, appointment_id=appointment_id, provider_id=provider_id, action=CalendarSyncAction.SYNCED
    )
    assert second is None


def test_record_allows_synced_and_reverted_for_the_same_appointment(db) -> None:
    appointment_id = uuid.uuid4()
    provider_id = uuid.uuid4()

    synced = crud.calendar_sync_log.record(
        db, appointment_id=appointment_id, provider_id=provider_id, action=CalendarSyncAction.SYNCED
    )
    db.commit()
    reverted = crud.calendar_sync_log.record(
        db, appointment_id=appointment_id, provider_id=provider_id, action=CalendarSyncAction.REVERTED
    )
    db.commit()

    assert synced is not None
    assert reverted is not None


def test_get_finds_the_row_for_an_appointment_and_action(db) -> None:
    appointment_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    crud.calendar_sync_log.record(
        db, appointment_id=appointment_id, provider_id=provider_id, action=CalendarSyncAction.SYNCED
    )
    db.commit()

    row = crud.calendar_sync_log.get(db, appointment_id=appointment_id, action=CalendarSyncAction.SYNCED)
    assert row is not None
    assert crud.calendar_sync_log.get(db, appointment_id=appointment_id, action=CalendarSyncAction.REVERTED) is None


def test_sync_calendar_task_records_a_row(db) -> None:
    appointment_id = uuid.uuid4()
    provider_id = uuid.uuid4()

    sync_calendar_task.delay(str(appointment_id), str(provider_id), "synced")

    row = db.query(CalendarSyncLog).filter_by(appointment_id=appointment_id).one()
    assert row.action == CalendarSyncAction.SYNCED
    assert row.provider_id == provider_id
    assert row.external_event_id is None


def test_sync_calendar_task_is_idempotent_on_replay(db) -> None:
    appointment_id = uuid.uuid4()
    provider_id = uuid.uuid4()

    sync_calendar_task.delay(str(appointment_id), str(provider_id), "synced")
    sync_calendar_task.delay(str(appointment_id), str(provider_id), "synced")  # e.g. Temporal retry

    rows = db.query(CalendarSyncLog).filter_by(appointment_id=appointment_id).all()
    assert len(rows) == 1


def test_sync_calendar_task_stub_mode_never_calls_the_real_api(db, monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("google_calendar.create_event should not be called when disabled")

    monkeypatch.setattr("app.tasks.calendar_sync.google_calendar.create_event", _boom)
    appointment = _make_confirmed_appointment(db)

    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "synced")

    row = db.query(CalendarSyncLog).filter_by(appointment_id=appointment.id).one()
    assert row.external_event_id is None


def test_sync_calendar_task_creates_a_real_event_when_enabled(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "google_calendar_enabled", True)
    calls = []
    monkeypatch.setattr(
        "app.tasks.calendar_sync.google_calendar.create_event",
        lambda **kwargs: (calls.append(kwargs), "google-event-123")[1],
    )
    appointment = _make_confirmed_appointment(db)

    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "synced")

    row = db.query(CalendarSyncLog).filter_by(appointment_id=appointment.id).one()
    assert row.external_event_id == "google-event-123"
    assert len(calls) == 1
    assert calls[0]["start"] == appointment.slot.start_time


def test_sync_calendar_task_deletes_the_real_event_on_revert_when_enabled(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "google_calendar_enabled", True)
    monkeypatch.setattr(
        "app.tasks.calendar_sync.google_calendar.create_event", lambda **kwargs: "google-event-456"
    )
    appointment = _make_confirmed_appointment(db)
    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "synced")

    deleted = []
    monkeypatch.setattr(
        "app.tasks.calendar_sync.google_calendar.delete_event", lambda event_id: deleted.append(event_id)
    )
    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "reverted")

    assert deleted == ["google-event-456"]
    reverted_row = crud.calendar_sync_log.get(
        db, appointment_id=appointment.id, action=CalendarSyncAction.REVERTED
    )
    assert reverted_row is not None


def test_sync_calendar_task_records_rescheduled_in_stub_mode(db) -> None:
    appointment = _make_confirmed_appointment(db)
    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "synced")

    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "rescheduled")

    rows = [
        r
        for r in crud.calendar_sync_log.list_recent(db, appointment_id=appointment.id)
        if r.action == CalendarSyncAction.RESCHEDULED
    ]
    assert len(rows) == 1


def test_sync_calendar_task_allows_multiple_reschedules_for_the_same_appointment(db) -> None:
    # Unlike SYNCED/REVERTED, RESCHEDULED has no once-per-appointment
    # uniqueness — a booking can genuinely be moved more than once.
    appointment = _make_confirmed_appointment(db)
    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "synced")

    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "rescheduled")
    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "rescheduled")

    rows = [
        r
        for r in crud.calendar_sync_log.list_recent(db, appointment_id=appointment.id)
        if r.action == CalendarSyncAction.RESCHEDULED
    ]
    assert len(rows) == 2


def test_sync_calendar_task_updates_the_real_event_time_on_reschedule_when_enabled(db, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "google_calendar_enabled", True)
    monkeypatch.setattr(
        "app.tasks.calendar_sync.google_calendar.create_event", lambda **kwargs: "google-event-789"
    )
    appointment = _make_confirmed_appointment(db)
    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "synced")

    calls = []
    monkeypatch.setattr(
        "app.tasks.calendar_sync.google_calendar.update_event",
        lambda event_id, **kwargs: calls.append((event_id, kwargs)),
    )

    sync_calendar_task.delay(str(appointment.id), str(appointment.provider_id), "rescheduled")

    assert len(calls) == 1
    event_id, kwargs = calls[0]
    assert event_id == "google-event-789"
    assert kwargs["start"] == appointment.slot.start_time

    rescheduled_row = [
        r
        for r in crud.calendar_sync_log.list_recent(db, appointment_id=appointment.id)
        if r.action == CalendarSyncAction.RESCHEDULED
    ][0]
    assert rescheduled_row.external_event_id == "google-event-789"

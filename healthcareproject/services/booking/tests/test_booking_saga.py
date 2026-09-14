import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app import crud
from app.activities import booking as booking_activities
from app.activities import reminder as reminder_activities
from app.db.session import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.outbox_event import OutboxEvent
from app.models.reminder_log import ReminderLog
from app.models.slot import Slot, SlotStatus
from app.workflows.booking_saga import BookingSagaInput, BookingSagaWorkflow
from app.workflows.reminder import ReminderWorkflow

TASK_QUEUE = "test-booking-saga"


def _make_pending_appointment(db):
    provider_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = crud.slot.create(db, provider_id=provider_id, start_time=start, end_time=start + timedelta(minutes=20))
    appointment = Appointment(
        id=uuid.uuid4(),
        patient_id=patient_id,
        provider_id=provider_id,
        slot_id=slot.id,
        status=AppointmentStatus.PENDING,
    )
    db.add(appointment)
    db.commit()
    return appointment, slot


async def test_saga_happy_path_confirms_appointment_and_reserves_slot(db) -> None:
    appointment, slot = _make_pending_appointment(db)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[BookingSagaWorkflow],
            activities=[
                booking_activities.validate_booking,
                booking_activities.reserve_slot,
                booking_activities.sync_calendar,
                booking_activities.revert_calendar_sync,
                booking_activities.billing_precheck,
                booking_activities.confirm_appointment,
                booking_activities.release_slot,
                booking_activities.mark_appointment_failed,
            ],
            activity_executor=ThreadPoolExecutor(max_workers=10),
        ):
            result = await env.client.execute_workflow(
                BookingSagaWorkflow.run,
                BookingSagaInput(
                    appointment_id=str(appointment.id),
                    patient_id=str(appointment.patient_id),
                    provider_id=str(appointment.provider_id),
                    slot_id=str(slot.id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert result.status == "confirmed"

    fresh_db = SessionLocal()
    try:
        refreshed_appointment = fresh_db.get(Appointment, appointment.id)
        refreshed_slot = fresh_db.get(Slot, slot.id)
        assert refreshed_appointment.status == AppointmentStatus.CONFIRMED
        assert refreshed_slot.status == SlotStatus.RESERVED
    finally:
        fresh_db.close()


async def test_saga_happy_path_schedules_a_reminder(db) -> None:
    """Confirms the saga starts ReminderWorkflow with the right id/input —
    NOT that the workflow resolves end-to-end. An earlier version of this
    test also waited on the child's real completion via the time-skipping
    test env; that was found to be genuinely flaky specifically when run
    alongside this repo's many OTHER WorkflowEnvironment-based tests in one
    pytest session (consistent "No completion event found"/RPC timeout
    errors under that load, never in isolation) — infra fragility in the
    ephemeral test server, not a defect in the saga or ReminderWorkflow
    themselves (send_reminder's own behavior is covered directly and
    reliably in test_reminder.py; ReminderWorkflow's durable-sleep-then-
    activity behavior is covered by test_reschedule.py's still-uses-
    .result() end-to-end test, which stayed reliable — only this file's
    combination with the rest of the suite was the flaky one)."""
    appointment, slot = _make_pending_appointment(db)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[BookingSagaWorkflow, ReminderWorkflow],
            activities=[
                booking_activities.validate_booking,
                booking_activities.reserve_slot,
                booking_activities.sync_calendar,
                booking_activities.revert_calendar_sync,
                booking_activities.billing_precheck,
                booking_activities.confirm_appointment,
                booking_activities.release_slot,
                booking_activities.mark_appointment_failed,
                reminder_activities.send_reminder,
            ],
            activity_executor=ThreadPoolExecutor(max_workers=10),
        ):
            result = await env.client.execute_workflow(
                BookingSagaWorkflow.run,
                BookingSagaInput(
                    appointment_id=str(appointment.id),
                    patient_id=str(appointment.patient_id),
                    provider_id=str(appointment.provider_id),
                    slot_id=str(slot.id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert result.status == "confirmed"
    # confirm_appointment normalizes a naive start_time to aware UTC before
    # building the id (SQLite round-trips DateTime(timezone=True) as naive
    # — same recurring quirk as elsewhere in this codebase); match that
    # normalization here rather than asserting on the raw ORM value.
    expected_start = slot.start_time if slot.start_time.tzinfo is not None else slot.start_time.replace(tzinfo=timezone.utc)
    assert result.reminder_workflow_id == f"reminder-{appointment.id}-for-{expected_start.isoformat()}"


async def test_saga_happy_path_publishes_appointment_booked_event(db, monkeypatch) -> None:
    from kafka_shared import Topic

    appointment, slot = _make_pending_appointment(db)
    calls = []
    monkeypatch.setattr(
        "app.activities.booking.publish",
        lambda db, event_type, payload, *, actor=None: calls.append((event_type, payload, actor)),
    )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[BookingSagaWorkflow],
            activities=[
                booking_activities.validate_booking,
                booking_activities.reserve_slot,
                booking_activities.sync_calendar,
                booking_activities.revert_calendar_sync,
                booking_activities.billing_precheck,
                booking_activities.confirm_appointment,
                booking_activities.release_slot,
                booking_activities.mark_appointment_failed,
            ],
            activity_executor=ThreadPoolExecutor(max_workers=10),
        ):
            await env.client.execute_workflow(
                BookingSagaWorkflow.run,
                BookingSagaInput(
                    appointment_id=str(appointment.id),
                    patient_id=str(appointment.patient_id),
                    provider_id=str(appointment.provider_id),
                    slot_id=str(slot.id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert len(calls) == 1
    event_type, payload, actor = calls[0]
    assert event_type == Topic.APPOINTMENT_BOOKED
    assert payload == {
        "appointment_id": str(appointment.id),
        "patient_id": str(appointment.patient_id),
        "provider_id": str(appointment.provider_id),
        "slot_id": str(slot.id),
    }
    assert actor == str(appointment.patient_id)


async def test_saga_happy_path_enqueues_calendar_sync(db, monkeypatch) -> None:
    appointment, slot = _make_pending_appointment(db)
    calls = []
    monkeypatch.setattr(
        "app.activities.booking.sync_calendar_task.delay",
        lambda appointment_id, provider_id, action: calls.append((appointment_id, provider_id, action)),
    )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[BookingSagaWorkflow],
            activities=[
                booking_activities.validate_booking,
                booking_activities.reserve_slot,
                booking_activities.sync_calendar,
                booking_activities.revert_calendar_sync,
                booking_activities.billing_precheck,
                booking_activities.confirm_appointment,
                booking_activities.release_slot,
                booking_activities.mark_appointment_failed,
            ],
            activity_executor=ThreadPoolExecutor(max_workers=10),
        ):
            result = await env.client.execute_workflow(
                BookingSagaWorkflow.run,
                BookingSagaInput(
                    appointment_id=str(appointment.id),
                    patient_id=str(appointment.patient_id),
                    provider_id=str(appointment.provider_id),
                    slot_id=str(slot.id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert result.status == "confirmed"
    # Fire-and-forget: exactly one enqueue, "synced" — never "reverted" on
    # a saga that never failed.
    assert calls == [(str(appointment.id), str(appointment.provider_id), "synced")]


async def test_saga_compensates_on_billing_failure(db, monkeypatch) -> None:
    appointment, slot = _make_pending_appointment(db)
    calls = []
    monkeypatch.setattr(
        "app.activities.booking.sync_calendar_task.delay",
        lambda appointment_id, provider_id, action: calls.append((appointment_id, provider_id, action)),
    )

    @activity.defn(name="billing_precheck")
    def failing_billing_precheck(inp) -> None:
        raise ApplicationError("billing_declined", non_retryable=True)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[BookingSagaWorkflow],
            activities=[
                booking_activities.validate_booking,
                booking_activities.reserve_slot,
                booking_activities.sync_calendar,
                booking_activities.revert_calendar_sync,
                failing_billing_precheck,
                booking_activities.confirm_appointment,
                booking_activities.release_slot,
                booking_activities.mark_appointment_failed,
            ],
            activity_executor=ThreadPoolExecutor(max_workers=10),
        ):
            result = await env.client.execute_workflow(
                BookingSagaWorkflow.run,
                BookingSagaInput(
                    appointment_id=str(appointment.id),
                    patient_id=str(appointment.patient_id),
                    provider_id=str(appointment.provider_id),
                    slot_id=str(slot.id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert result.status == "failed"

    fresh_db = SessionLocal()
    try:
        refreshed_appointment = fresh_db.get(Appointment, appointment.id)
        refreshed_slot = fresh_db.get(Slot, slot.id)
        # Compensated: slot released back to open, appointment marked failed
        # — never left half-reserved with no valid appointment (design §7).
        assert refreshed_appointment.status == AppointmentStatus.FAILED
        assert refreshed_slot.status == SlotStatus.OPEN
    finally:
        fresh_db.close()

    # Calendar sync compensated too, same as the slot — "synced" from the
    # forward step, then "reverted" from the compensation that ran after
    # billing declined.
    assert calls == [
        (str(appointment.id), str(appointment.provider_id), "synced"),
        (str(appointment.id), str(appointment.provider_id), "reverted"),
    ]

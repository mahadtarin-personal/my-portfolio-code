import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app import crud
from app.activities import booking as booking_activities
from app.activities import reschedule as reschedule_activities
from app.db.session import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.slot import Slot, SlotStatus
from app.workflows.reschedule import RescheduleAppointmentInput, RescheduleAppointmentWorkflow

TASK_QUEUE = "test-reschedule"


def _setup(db):
    provider_id = uuid.uuid4()
    now = datetime.now(timezone.utc) + timedelta(days=1)
    old_slot = crud.slot.create(
        db, provider_id=provider_id, start_time=now, end_time=now + timedelta(minutes=30)
    )
    new_start = now + timedelta(hours=2)
    new_slot = crud.slot.create(
        db,
        provider_id=provider_id,
        start_time=new_start,
        end_time=new_start + timedelta(minutes=30),
    )
    old_slot.status = SlotStatus.RESERVED
    db.commit()

    appointment = Appointment(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        provider_id=provider_id,
        slot_id=old_slot.id,
        status=AppointmentStatus.CONFIRMED,
    )
    db.add(appointment)
    db.commit()
    return appointment, old_slot, new_slot


def _worker(env):
    return Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[RescheduleAppointmentWorkflow],
        activities=[
            booking_activities.release_slot,
            reschedule_activities.reserve_new_slot,
            reschedule_activities.swap_appointment_slot,
            reschedule_activities.release_old_slot_and_promote_waitlist,
        ],
        activity_executor=ThreadPoolExecutor(max_workers=10),
    )


async def test_reschedule_happy_path_moves_appointment_to_new_slot(db) -> None:
    appointment, old_slot, new_slot = _setup(db)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env):
            result = await env.client.execute_workflow(
                RescheduleAppointmentWorkflow.run,
                RescheduleAppointmentInput(
                    appointment_id=str(appointment.id),
                    old_slot_id=str(old_slot.id),
                    new_slot_id=str(new_slot.id),
                    provider_id=str(appointment.provider_id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert result.status == "confirmed"

    fresh_db = SessionLocal()
    try:
        refreshed_appointment = fresh_db.get(Appointment, appointment.id)
        refreshed_old_slot = fresh_db.get(Slot, old_slot.id)
        refreshed_new_slot = fresh_db.get(Slot, new_slot.id)
        assert refreshed_appointment.slot_id == new_slot.id
        assert refreshed_appointment.status == AppointmentStatus.CONFIRMED
        assert refreshed_old_slot.status == SlotStatus.OPEN
        assert refreshed_new_slot.status == SlotStatus.RESERVED
    finally:
        fresh_db.close()


async def test_reschedule_happy_path_publishes_appointment_rescheduled_event(db, monkeypatch) -> None:
    from kafka_shared import Topic

    appointment, old_slot, new_slot = _setup(db)
    calls = []
    monkeypatch.setattr(
        "app.activities.reschedule.publish",
        lambda db, event_type, payload, *, actor=None: calls.append((event_type, payload, actor)),
    )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env):
            await env.client.execute_workflow(
                RescheduleAppointmentWorkflow.run,
                RescheduleAppointmentInput(
                    appointment_id=str(appointment.id),
                    old_slot_id=str(old_slot.id),
                    new_slot_id=str(new_slot.id),
                    provider_id=str(appointment.provider_id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert len(calls) == 1
    event_type, payload, actor = calls[0]
    assert event_type == Topic.APPOINTMENT_RESCHEDULED
    assert payload == {
        "appointment_id": str(appointment.id),
        "patient_id": str(appointment.patient_id),
        "provider_id": str(appointment.provider_id),
        "old_slot_id": str(old_slot.id),
        "new_slot_id": str(new_slot.id),
    }
    assert actor == str(appointment.patient_id)


async def test_reschedule_moves_a_scheduled_reminder_to_rescheduled(db) -> None:
    from app.models.reminder_log import ReminderLog, ReminderStatus

    appointment, old_slot, new_slot = _setup(db)
    crud.reminder_log.record(
        db,
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        provider_id=appointment.provider_id,
        appointment_start_time=old_slot.start_time,
        appointment_status="confirmed",
    )
    db.commit()

    # _worker() below deliberately doesn't register ReminderWorkflow, so
    # the freshly (re)scheduled child workflow gets started (recorded in
    # history) but never actually runs — nothing carries the row past
    # RESCHEDULED to SENT before this test observes the transition it's
    # actually testing. (A dedicated end-to-end version of this exists in
    # test_booking_saga.py, which does register the workflow.)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env):
            await env.client.execute_workflow(
                RescheduleAppointmentWorkflow.run,
                RescheduleAppointmentInput(
                    appointment_id=str(appointment.id),
                    old_slot_id=str(old_slot.id),
                    new_slot_id=str(new_slot.id),
                    provider_id=str(appointment.provider_id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    fresh_db = SessionLocal()
    try:
        reminder = fresh_db.query(ReminderLog).filter_by(appointment_id=appointment.id).one()
        assert reminder.status == ReminderStatus.RESCHEDULED
        assert reminder.appointment_start_time == new_slot.start_time
    finally:
        fresh_db.close()


async def test_reschedule_reminder_workflow_resolves_for_the_new_time(db) -> None:
    """End-to-end version of the test above — a real ReminderWorkflow
    registered and allowed to run, its durable sleep resolved via the
    time-skipping test env, actually sending the reminder for the NEW
    (post-reschedule) time."""
    from app.activities import reminder as reminder_activities
    from app.models.reminder_log import ReminderLog, ReminderStatus
    from app.workflows.reminder import ReminderWorkflow

    # Near-term slots (not _setup()'s usual ~1-day-ahead), so
    # ReminderWorkflow's durable sleep only needs to skip a few simulated
    # minutes, not ~24+ hours — see the matching comment in
    # test_booking_saga.py for why the larger skip was flaky here.
    provider_id = uuid.uuid4()
    now = datetime.now(timezone.utc) + timedelta(minutes=10)
    old_slot = crud.slot.create(db, provider_id=provider_id, start_time=now, end_time=now + timedelta(minutes=30))
    new_start = now + timedelta(minutes=30)
    new_slot = crud.slot.create(
        db, provider_id=provider_id, start_time=new_start, end_time=new_start + timedelta(minutes=30)
    )
    old_slot.status = SlotStatus.RESERVED
    db.commit()
    appointment = Appointment(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        provider_id=provider_id,
        slot_id=old_slot.id,
        status=AppointmentStatus.CONFIRMED,
    )
    db.add(appointment)
    db.commit()
    crud.reminder_log.record(
        db,
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        provider_id=appointment.provider_id,
        appointment_start_time=old_slot.start_time,
        appointment_status="confirmed",
    )
    db.commit()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        worker = Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[RescheduleAppointmentWorkflow, ReminderWorkflow],
            activities=[
                booking_activities.release_slot,
                reschedule_activities.reserve_new_slot,
                reschedule_activities.swap_appointment_slot,
                reschedule_activities.release_old_slot_and_promote_waitlist,
                reminder_activities.send_reminder,
            ],
            activity_executor=ThreadPoolExecutor(max_workers=10),
        )
        async with worker:
            result = await env.client.execute_workflow(
                RescheduleAppointmentWorkflow.run,
                RescheduleAppointmentInput(
                    appointment_id=str(appointment.id),
                    old_slot_id=str(old_slot.id),
                    new_slot_id=str(new_slot.id),
                    provider_id=str(appointment.provider_id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            assert result.reminder_workflow_id is not None
            # See the matching comment in test_booking_saga.py — awaiting
            # the result directly (not an explicit env.sleep()) is what
            # actually works reliably here.
            await env.client.get_workflow_handle(result.reminder_workflow_id).result()

    fresh_db = SessionLocal()
    try:
        reminder = fresh_db.query(ReminderLog).filter_by(appointment_id=appointment.id).one()
        assert reminder.status == ReminderStatus.SENT
    finally:
        fresh_db.close()


async def test_reschedule_enqueues_a_calendar_reschedule(db, monkeypatch) -> None:
    appointment, old_slot, new_slot = _setup(db)
    calls = []
    monkeypatch.setattr(
        "app.activities.reschedule.sync_calendar_task.delay",
        lambda appointment_id, provider_id, action: calls.append((appointment_id, provider_id, action)),
    )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env):
            await env.client.execute_workflow(
                RescheduleAppointmentWorkflow.run,
                RescheduleAppointmentInput(
                    appointment_id=str(appointment.id),
                    old_slot_id=str(old_slot.id),
                    new_slot_id=str(new_slot.id),
                    provider_id=str(appointment.provider_id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert calls == [(str(appointment.id), str(appointment.provider_id), "rescheduled")]


async def test_reschedule_fails_cleanly_if_new_slot_already_taken(db) -> None:
    appointment, old_slot, new_slot = _setup(db)
    new_slot.status = SlotStatus.RESERVED  # already taken by someone else
    db.commit()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env):
            result = await env.client.execute_workflow(
                RescheduleAppointmentWorkflow.run,
                RescheduleAppointmentInput(
                    appointment_id=str(appointment.id),
                    old_slot_id=str(old_slot.id),
                    new_slot_id=str(new_slot.id),
                    provider_id=str(appointment.provider_id),
                ),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert result.status == "failed"

    fresh_db = SessionLocal()
    try:
        refreshed_appointment = fresh_db.get(Appointment, appointment.id)
        refreshed_old_slot = fresh_db.get(Slot, old_slot.id)
        assert refreshed_appointment.slot_id == old_slot.id  # untouched
        assert refreshed_appointment.status == AppointmentStatus.CONFIRMED
        assert refreshed_old_slot.status == SlotStatus.RESERVED  # untouched
    finally:
        fresh_db.close()

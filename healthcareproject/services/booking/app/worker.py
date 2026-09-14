import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from logging_shared import configure_logging
from temporalio.client import Client, Schedule, ScheduleActionStartWorkflow, ScheduleIntervalSpec, ScheduleSpec
from temporalio.service import RPCError
from temporalio.worker import Worker

from app.activities import booking as booking_activities
from app.activities import reminder as reminder_activities
from app.activities import reschedule as reschedule_activities
from app.activities import slot_generation as slot_generation_activities
from app.core.config import get_settings
from app.core.temporal import connect_with_retry
from app.workflows.booking_saga import BookingSagaWorkflow
from app.workflows.reminder import ReminderWorkflow
from app.workflows.reschedule import RescheduleAppointmentWorkflow
from app.workflows.slot_generation import (
    DEFAULT_DAYS_AHEAD,
    GenerateSlotsScheduledWorkflow,
    ReconcileProviderSlotsWorkflow,
)

configure_logging("booking-worker")
logger = logging.getLogger("booking.worker")

SLOT_GENERATION_SCHEDULE_ID = "slot-generation-daily"


async def ensure_slot_generation_schedule(client: Client, task_queue: str) -> None:
    """Self-installing: safe to call on every worker startup. Runs the
    recurring counterpart to POST /slots/generate on a Temporal Schedule
    instead of Celery — reuses the server/worker that already exist for
    the booking saga rather than needing a new broker + beat process."""
    handle = client.get_schedule_handle(SLOT_GENERATION_SCHEDULE_ID)
    try:
        await handle.describe()
        logger.info("schedule %s already exists", SLOT_GENERATION_SCHEDULE_ID)
        return
    except RPCError:
        pass  # not found — create it below

    await client.create_schedule(
        SLOT_GENERATION_SCHEDULE_ID,
        Schedule(
            action=ScheduleActionStartWorkflow(
                GenerateSlotsScheduledWorkflow.run,
                DEFAULT_DAYS_AHEAD,
                id="slot-generation-scheduled",
                task_queue=task_queue,
            ),
            spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(hours=24))]),
        ),
    )
    logger.info("created schedule %s", SLOT_GENERATION_SCHEDULE_ID)


async def main() -> None:
    settings = get_settings()
    client = await connect_with_retry(settings.temporal_address, settings.temporal_namespace)
    await ensure_slot_generation_schedule(client, settings.temporal_task_queue)

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[
            BookingSagaWorkflow,
            GenerateSlotsScheduledWorkflow,
            RescheduleAppointmentWorkflow,
            ReconcileProviderSlotsWorkflow,
            ReminderWorkflow,
        ],
        activities=[
            booking_activities.validate_booking,
            booking_activities.reserve_slot,
            booking_activities.sync_calendar,
            booking_activities.revert_calendar_sync,
            booking_activities.billing_precheck,
            booking_activities.confirm_appointment,
            booking_activities.release_slot,
            booking_activities.mark_appointment_failed,
            slot_generation_activities.list_provider_ids,
            slot_generation_activities.generate_slots_for_one_provider,
            reschedule_activities.reserve_new_slot,
            reschedule_activities.swap_appointment_slot,
            reschedule_activities.release_old_slot_and_promote_waitlist,
            reminder_activities.send_reminder,
        ],
        # Activities are plain `def`, not `async def` (they call sync
        # SQLAlchemy) — Temporal requires an executor for sync activities.
        activity_executor=ThreadPoolExecutor(max_workers=10),
    )
    logger.info(
        "booking worker started; address=%s namespace=%s task_queue=%s",
        settings.temporal_address,
        settings.temporal_namespace,
        settings.temporal_task_queue,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

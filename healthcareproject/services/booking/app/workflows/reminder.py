from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.activities.reminder import SendReminderInput, send_reminder

REMINDER_LEAD_TIME = timedelta(minutes=30)


@dataclass
class ReminderWorkflowInput:
    appointment_id: str
    patient_id: str
    provider_id: str
    scheduled_for_start_time: str  # ISO — the slot start_time this run targets


@workflow.defn
class ReminderWorkflow:
    """Durable replacement for the old Celery-eta reminder: started as an
    ABANDON-policy child right after confirm_appointment/swap_appointment_slot
    succeed (see booking_saga.py / reschedule.py), so it keeps running
    independently of its parent's own lifecycle — the booking saga
    completes in seconds, this workflow can still be sleeping 30 minutes
    later.

    workflow.sleep() is a durable timer, not a real-time wait: if the
    worker crashes or restarts while this is asleep, Temporal replays this
    workflow from its persisted history on the next worker startup and the
    sleep resumes exactly where it left off. That's the actual fix for the
    gap this replaced — a bare `send_reminder_task.apply_async(eta=...)`
    call made outside the DB transaction that recorded the reminder as
    SCHEDULED, with no durability of its own: a crash between the two
    left a SCHEDULED row with no task ever actually enqueued to honor it.

    A reschedule doesn't cancel this workflow — it starts a brand new
    ReminderWorkflow for the new time instead (a different workflow id,
    since the target time changed), leaving this one still asleep for the
    OLD time. When it wakes, send_reminder's own staleness check (comparing
    scheduled_for_start_time against the appointment's current slot) sees
    the mismatch and backs off untouched — same self-detecting-staleness
    design the old Celery version used, now just durably scheduled instead
    of broker-scheduled."""

    @workflow.run
    async def run(self, inp: ReminderWorkflowInput) -> None:
        scheduled_for = datetime.fromisoformat(inp.scheduled_for_start_time)
        if scheduled_for.tzinfo is None:
            scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)
        reminder_at = scheduled_for - REMINDER_LEAD_TIME
        delay = (reminder_at - workflow.now()).total_seconds()
        if delay > 0:
            await workflow.sleep(delay)

        await workflow.execute_activity(
            send_reminder,
            SendReminderInput(
                appointment_id=inp.appointment_id,
                patient_id=inp.patient_id,
                provider_id=inp.provider_id,
                scheduled_for_start_time=inp.scheduled_for_start_time,
            ),
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )

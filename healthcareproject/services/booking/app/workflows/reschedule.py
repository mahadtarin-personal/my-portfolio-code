from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from app.activities.booking import ReleaseSlotInput, release_slot
    from app.activities.reschedule import (
        ReleaseOldSlotInput,
        ReserveNewSlotInput,
        SwapAppointmentSlotInput,
        release_old_slot_and_promote_waitlist,
        reserve_new_slot,
        swap_appointment_slot,
    )
    from app.workflows.reminder import ReminderWorkflow, ReminderWorkflowInput


@dataclass
class RescheduleAppointmentInput:
    appointment_id: str
    old_slot_id: str
    new_slot_id: str
    provider_id: str


@dataclass
class RescheduleAppointmentResult:
    appointment_id: str
    status: str  # "confirmed" | "failed"
    reason: str | None = None
    reminder_workflow_id: str | None = None


STEP_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=20),
    maximum_attempts=5,
)
# Compensation, and the final release+promote step, must not silently give
# up — a stuck slot or a missed waitlist promotion is worse than a slow one.
COMPENSATION_RETRY = RetryPolicy(maximum_attempts=10)


@workflow.defn
class RescheduleAppointmentWorkflow:
    """Reserve new slot -> swap the appointment onto it -> release the old
    slot (which also promotes whoever's waiting for it, see
    app/services/waitlist_promotion.py). Reused for both a patient-initiated
    reschedule and a waitlist promotion that shifts an existing appointment.

    If reserving the new slot fails, nothing has changed — no compensation
    needed. If swapping fails after the new slot was reserved, the new slot
    is released (compensation) so the original confirmed appointment is left
    completely untouched. The final release-old-slot step is not
    compensated on failure, since by then the reschedule itself already
    succeeded — it just gets retried aggressively instead."""

    @workflow.run
    async def run(self, inp: RescheduleAppointmentInput) -> RescheduleAppointmentResult:
        reminder_workflow_id = None
        try:
            await workflow.execute_activity(
                reserve_new_slot,
                ReserveNewSlotInput(slot_id=inp.new_slot_id, provider_id=inp.provider_id),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=STEP_RETRY,
            )

            try:
                swap_result = await workflow.execute_activity(
                    swap_appointment_slot,
                    SwapAppointmentSlotInput(
                        appointment_id=inp.appointment_id,
                        old_slot_id=inp.old_slot_id,
                        new_slot_id=inp.new_slot_id,
                    ),
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=STEP_RETRY,
                )
                if swap_result.scheduled_for_start_time is not None:
                    # Same ABANDON + deterministic-id pattern as the
                    # booking saga (see booking_saga.py) — a fresh
                    # ReminderWorkflow for the NEW time, started
                    # independently of this workflow's own lifecycle. The
                    # workflow ID differs from any earlier one for this
                    # appointment (the target time changed), so it's a
                    # genuinely new workflow, not a duplicate-start
                    # against an old one still asleep for the old time.
                    reminder_workflow_id = (
                        f"reminder-{inp.appointment_id}-for-{swap_result.scheduled_for_start_time}"
                    )
                    await workflow.start_child_workflow(
                        ReminderWorkflow.run,
                        ReminderWorkflowInput(
                            appointment_id=inp.appointment_id,
                            patient_id=swap_result.patient_id,
                            provider_id=swap_result.provider_id,
                            scheduled_for_start_time=swap_result.scheduled_for_start_time,
                        ),
                        id=reminder_workflow_id,
                        task_queue=workflow.info().task_queue,
                        parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                    )
            except ActivityError:
                # Compensate before re-raising to the outer handler — the
                # new slot was reserved but never actually claimed by this
                # appointment, so it must go back to open.
                await workflow.execute_activity(
                    release_slot,
                    ReleaseSlotInput(
                        appointment_id=inp.appointment_id,
                        slot_id=inp.new_slot_id,
                        provider_id=inp.provider_id,
                    ),
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=COMPENSATION_RETRY,
                )
                raise
        except ActivityError as exc:
            reason = str(exc.cause) if exc.cause else str(exc)
            return RescheduleAppointmentResult(
                appointment_id=inp.appointment_id, status="failed", reason=reason
            )

        await workflow.execute_activity(
            release_old_slot_and_promote_waitlist,
            ReleaseOldSlotInput(provider_id=inp.provider_id, old_slot_id=inp.old_slot_id),
            start_to_close_timeout=timedelta(seconds=20),
            retry_policy=COMPENSATION_RETRY,
        )

        return RescheduleAppointmentResult(
            appointment_id=inp.appointment_id,
            status="confirmed",
            reminder_workflow_id=reminder_workflow_id,
        )

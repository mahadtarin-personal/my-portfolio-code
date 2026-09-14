from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from app.activities.booking import (
        BillingPrecheckInput,
        CalendarSyncInput,
        ConfirmInput,
        ReleaseSlotInput,
        ReserveSlotInput,
        ValidateInput,
        billing_precheck,
        confirm_appointment,
        mark_appointment_failed,
        release_slot,
        reserve_slot,
        revert_calendar_sync,
        sync_calendar,
        validate_booking,
    )
    from app.workflows.reminder import ReminderWorkflow, ReminderWorkflowInput


@dataclass
class BookingSagaInput:
    appointment_id: str
    patient_id: str
    provider_id: str
    slot_id: str


@dataclass
class BookingSagaResult:
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
# Compensations must not silently give up — a stuck slot/appointment from a
# half-undone saga is worse than a slow one.
COMPENSATION_RETRY = RetryPolicy(maximum_attempts=10)


@workflow.defn
class BookingSagaWorkflow:
    """Validate -> Reserve slot -> Sync calendar -> Billing pre-check ->
    Confirm (design §5.2).

    No built-in saga primitive in Temporal: compensations are hand-rolled
    as an explicit list, appended to only after the corresponding forward
    step succeeds, and run in reverse on any activity failure."""

    @workflow.run
    async def run(self, saga_input: BookingSagaInput) -> BookingSagaResult:
        compensations: list[tuple] = []

        try:
            await workflow.execute_activity(
                validate_booking,
                ValidateInput(
                    slot_id=saga_input.slot_id,
                    provider_id=saga_input.provider_id,
                    patient_id=saga_input.patient_id,
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=STEP_RETRY,
            )

            await workflow.execute_activity(
                reserve_slot,
                ReserveSlotInput(
                    appointment_id=saga_input.appointment_id,
                    slot_id=saga_input.slot_id,
                    provider_id=saga_input.provider_id,
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=STEP_RETRY,
            )
            compensations.append(
                (
                    release_slot,
                    ReleaseSlotInput(
                        appointment_id=saga_input.appointment_id,
                        slot_id=saga_input.slot_id,
                        provider_id=saga_input.provider_id,
                    ),
                )
            )

            await workflow.execute_activity(
                sync_calendar,
                CalendarSyncInput(
                    appointment_id=saga_input.appointment_id,
                    provider_id=saga_input.provider_id,
                ),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=STEP_RETRY,
            )
            compensations.append(
                (
                    revert_calendar_sync,
                    CalendarSyncInput(
                        appointment_id=saga_input.appointment_id,
                        provider_id=saga_input.provider_id,
                    ),
                )
            )

            await workflow.execute_activity(
                billing_precheck,
                BillingPrecheckInput(
                    appointment_id=saga_input.appointment_id, patient_id=saga_input.patient_id
                ),
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=STEP_RETRY,
            )

            confirm_result = await workflow.execute_activity(
                confirm_appointment,
                ConfirmInput(appointment_id=saga_input.appointment_id),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=STEP_RETRY,
            )
            reminder_workflow_id = None
            if confirm_result.scheduled_for_start_time is not None:
                # ABANDON: this child keeps running independently of this
                # workflow's own lifecycle — the saga completes in
                # seconds, ReminderWorkflow can still be asleep 30 minutes
                # later. Deterministic id (appointment + the exact time it
                # targets) so a retried confirm_appointment attempt can't
                # start a second reminder for the same booking.
                reminder_workflow_id = (
                    f"reminder-{saga_input.appointment_id}-for-{confirm_result.scheduled_for_start_time}"
                )
                await workflow.start_child_workflow(
                    ReminderWorkflow.run,
                    ReminderWorkflowInput(
                        appointment_id=saga_input.appointment_id,
                        patient_id=confirm_result.patient_id,
                        provider_id=confirm_result.provider_id,
                        scheduled_for_start_time=confirm_result.scheduled_for_start_time,
                    ),
                    id=reminder_workflow_id,
                    task_queue=workflow.info().task_queue,
                    parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                )
            return BookingSagaResult(
                appointment_id=saga_input.appointment_id,
                status="confirmed",
                reminder_workflow_id=reminder_workflow_id,
            )

        except ActivityError as exc:
            for comp_activity, comp_input in reversed(compensations):
                await workflow.execute_activity(
                    comp_activity,
                    comp_input,
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=COMPENSATION_RETRY,
                )
            await workflow.execute_activity(
                mark_appointment_failed,
                ConfirmInput(appointment_id=saga_input.appointment_id),
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=COMPENSATION_RETRY,
            )
            reason = str(exc.cause) if exc.cause else str(exc)
            return BookingSagaResult(
                appointment_id=saga_input.appointment_id, status="failed", reason=reason
            )

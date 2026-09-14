from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timezone

from kafka_shared import Topic
from sqlalchemy import update
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError

from app.core import cache
from app.core.config import get_settings
from app.crud import reminder_log as reminder_log_crud
from app.db.session import session_scope
from app.models.appointment import Appointment
from app.models.calendar_sync_log import CalendarSyncAction
from app.models.slot import Slot, SlotStatus
from app.services.events import publish
from app.services.waitlist_promotion import PromotionAction, promote_next_waitlisted
from app.tasks.calendar_sync import sync_calendar_task
from app.workflows.booking_saga import BookingSagaInput, BookingSagaWorkflow


@dataclass
class ReserveNewSlotInput:
    slot_id: str
    provider_id: str


@dataclass
class SwapAppointmentSlotInput:
    appointment_id: str
    old_slot_id: str
    new_slot_id: str


@dataclass
class ReleaseOldSlotInput:
    provider_id: str
    old_slot_id: str


@dataclass
class SwapAppointmentSlotResult:
    """None-shaped fields mean "nothing to remind" — either this attempt
    lost the idempotency race (already swapped) or the appointment
    genuinely vanished; the workflow only starts a fresh ReminderWorkflow
    when scheduled_for_start_time is not None."""

    patient_id: str | None
    provider_id: str | None
    scheduled_for_start_time: str | None


@activity.defn
def reserve_new_slot(inp: ReserveNewSlotInput) -> None:
    """Same atomic-conditional-UPDATE pattern as booking's reserve_slot —
    safe under both a genuine race (someone else takes it first) and
    Temporal's own at-least-once activity retries."""
    with session_scope() as db:
        result = db.execute(
            update(Slot)
            .where(Slot.id == uuid.UUID(inp.slot_id), Slot.status == SlotStatus.OPEN)
            .values(status=SlotStatus.RESERVED)
        )
        if result.rowcount == 0:
            raise ApplicationError("slot_unavailable", non_retryable=True)

    cache.invalidate_slots(uuid.UUID(inp.provider_id))


@activity.defn
def swap_appointment_slot(inp: SwapAppointmentSlotInput) -> SwapAppointmentSlotResult:
    """Points the appointment at the new slot. Status stays CONFIRMED
    throughout — this is a relocation, not a new booking.

    The early return below (already swapped by a prior attempt of this
    same activity) is also what makes it safe to unconditionally reschedule
    the reminder and enqueue a calendar move further down — Temporal's
    at-least-once retries never reach that code a second time for the
    same real reschedule, so neither needs its own extra idempotency
    guard here."""
    appointment_id = uuid.UUID(inp.appointment_id)
    new_slot_id = uuid.UUID(inp.new_slot_id)
    with session_scope() as db:
        appointment = db.get(Appointment, appointment_id)
        if appointment is not None and appointment.slot_id == new_slot_id:
            # Already swapped by a prior attempt of this same activity
            # (Temporal's at-least-once retries) — event already published
            # then; publishing again would mint a second, differently-IDed
            # event for the same real reschedule.
            return SwapAppointmentSlotResult(
                patient_id=None, provider_id=None, scheduled_for_start_time=None
            )
        db.execute(
            update(Appointment).where(Appointment.id == appointment_id).values(slot_id=new_slot_id)
        )
        publish(
            db,
            Topic.APPOINTMENT_RESCHEDULED,
            {
                "appointment_id": inp.appointment_id,
                "patient_id": str(appointment.patient_id) if appointment else None,
                "provider_id": str(appointment.provider_id) if appointment else None,
                "old_slot_id": inp.old_slot_id,
                "new_slot_id": inp.new_slot_id,
            },
            actor=str(appointment.patient_id) if appointment else None,
        )

        new_start_time = None
        patient_id_str = None
        provider_id_str = None
        if appointment is not None:
            patient_id_str = str(appointment.patient_id)
            provider_id_str = str(appointment.provider_id)
            new_slot = db.get(Slot, new_slot_id)
            new_start_time = new_slot.start_time
            if new_start_time.tzinfo is None:
                new_start_time = new_start_time.replace(tzinfo=timezone.utc)
            # Same row, moved back to RESCHEDULED with the new time — not
            # a second row (see ReminderLog's docstring). No-ops cleanly
            # if no reminder was ever scheduled for this appointment.
            reminder_log_crud.reschedule(
                db, appointment_id=appointment_id, appointment_start_time=new_start_time
            )

    if new_start_time is not None:
        # sync_calendar_task stays a fire-and-forget Celery call — only
        # the reminder moved to Temporal (see workflows/reminder.py for
        # why). sync_calendar_task's own DB lookup picks up the
        # already-swapped slot, so it moves the real event to match
        # without needing the new time passed in explicitly.
        sync_calendar_task.delay(
            inp.appointment_id, provider_id_str, CalendarSyncAction.RESCHEDULED.value
        )

    return SwapAppointmentSlotResult(
        patient_id=patient_id_str,
        provider_id=provider_id_str,
        scheduled_for_start_time=new_start_time.isoformat() if new_start_time is not None else None,
    )


@activity.defn
async def release_old_slot_and_promote_waitlist(inp: ReleaseOldSlotInput) -> None:
    """Releases the old slot, then checks whether anyone is waiting for it.
    Async (not the usual sync activity) because starting the promoted
    patient's workflow requires the Temporal client, which is async-only."""
    provider_id = uuid.UUID(inp.provider_id)
    old_slot_id = uuid.UUID(inp.old_slot_id)

    with session_scope() as db:
        db.execute(
            update(Slot)
            .where(Slot.id == old_slot_id, Slot.status == SlotStatus.RESERVED)
            .values(status=SlotStatus.OPEN)
        )
        result = promote_next_waitlisted(db, provider_id, old_slot_id)

    cache.invalidate_slots(provider_id)

    if result is None:
        return

    settings = get_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)

    try:
        if result.action == PromotionAction.SHIFT_EXISTING:
            from app.workflows.reschedule import RescheduleAppointmentInput, RescheduleAppointmentWorkflow

            await client.start_workflow(
                RescheduleAppointmentWorkflow.run,
                RescheduleAppointmentInput(
                    appointment_id=str(result.appointment.id),
                    old_slot_id=str(result.appointment.slot_id),
                    new_slot_id=str(result.slot_id),
                    provider_id=str(result.provider_id),
                ),
                id=f"reschedule-{result.appointment.id}-to-{result.slot_id}",
                task_queue=settings.temporal_task_queue,
            )
        else:
            await client.start_workflow(
                BookingSagaWorkflow.run,
                BookingSagaInput(
                    appointment_id=str(result.appointment.id),
                    patient_id=str(result.patient_id),
                    provider_id=str(result.provider_id),
                    slot_id=str(result.slot_id),
                ),
                id=f"booking-{result.appointment.id}",
                task_queue=settings.temporal_task_queue,
            )
    except WorkflowAlreadyStartedError:
        # This activity's own idempotency (promote_next_waitlisted's
        # waitlist entry gets marked fulfilled before this point, so a
        # Temporal-retried attempt of this whole activity would already
        # find nothing left to promote and return earlier) makes this a
        # true belt-and-suspenders case, same posture as the deterministic
        # workflow ID itself — not expected to fire, but starting a
        # duplicate workflow would be worse than swallowing this.
        pass

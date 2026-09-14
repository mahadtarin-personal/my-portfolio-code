from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timezone

from kafka_shared import Topic
from sqlalchemy import update
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.core import cache
from app.crud import reminder_log as reminder_log_crud
from app.db.session import session_scope
from app.models.appointment import Appointment, AppointmentStatus
from app.models.calendar_sync_log import CalendarSyncAction
from app.models.slot import Slot, SlotStatus
from app.services.events import publish
from app.tasks.calendar_sync import sync_calendar_task


@dataclass
class ValidateInput:
    slot_id: str
    provider_id: str
    patient_id: str


@dataclass
class CalendarSyncInput:
    appointment_id: str
    provider_id: str


@dataclass
class ReserveSlotInput:
    appointment_id: str
    slot_id: str
    provider_id: str


@dataclass
class BillingPrecheckInput:
    appointment_id: str
    patient_id: str


@dataclass
class ConfirmInput:
    appointment_id: str


@dataclass
class ConfirmResult:
    """None-shaped fields mean "nothing to remind" — either this attempt
    lost the idempotency race (already confirmed) or the appointment
    genuinely vanished; the workflow only starts ReminderWorkflow when
    scheduled_for_start_time is not None."""

    patient_id: str | None
    provider_id: str | None
    scheduled_for_start_time: str | None


@dataclass
class ReleaseSlotInput:
    appointment_id: str
    slot_id: str
    provider_id: str


@activity.defn
def validate_booking(inp: ValidateInput) -> None:
    with session_scope() as db:
        slot = db.get(Slot, uuid.UUID(inp.slot_id))
        if slot is None:
            raise ApplicationError("slot_not_found", non_retryable=True)
        if slot.provider_id != uuid.UUID(inp.provider_id):
            raise ApplicationError("slot_provider_mismatch", non_retryable=True)
        if slot.status != SlotStatus.OPEN:
            raise ApplicationError("slot_unavailable", non_retryable=True)


@activity.defn
def reserve_slot(inp: ReserveSlotInput) -> None:
    """Conditional UPDATE ... WHERE status='open' is what makes this safe
    both under a genuine booking race (design §5.1 — a second concurrent
    attempt just finds status no longer 'open') and under Temporal's own
    at-least-once activity retries (a retry after a prior successful commit
    also finds status no longer 'open', so it must disambiguate "someone
    else took it" from "I already reserved it last attempt" before failing."""
    slot_id = uuid.UUID(inp.slot_id)
    appointment_id = uuid.UUID(inp.appointment_id)
    with session_scope() as db:
        result = db.execute(
            update(Slot)
            .where(Slot.id == slot_id, Slot.status == SlotStatus.OPEN)
            .values(status=SlotStatus.RESERVED)
        )
        if result.rowcount == 0:
            slot = db.get(Slot, slot_id)
            already_ours = (
                slot is not None
                and slot.status == SlotStatus.RESERVED
                and slot.appointment is not None
                and slot.appointment.id == appointment_id
            )
            if not already_ours:
                raise ApplicationError("slot_unavailable", non_retryable=True)

        db.execute(
            update(Appointment)
            .where(
                Appointment.id == appointment_id,
                Appointment.status == AppointmentStatus.PENDING,
            )
            .values(status=AppointmentStatus.RESERVED)
        )

    cache.invalidate_slots(uuid.UUID(inp.provider_id))


@activity.defn
def sync_calendar(inp: CalendarSyncInput) -> None:
    """Saga step 3 (design §5). Fire-and-forget onto Celery — this
    activity's own job is just to enqueue the task and return; it does
    NOT wait for the Celery task to actually finish, matching "provider's
    calendar updated, not blocking the booking." Safe for Temporal to
    retry at-least-once: enqueuing the same task twice just means
    sync_calendar_task's own dedup (CalendarSyncLog's unique constraint)
    absorbs the second one."""
    sync_calendar_task.delay(inp.appointment_id, inp.provider_id, CalendarSyncAction.SYNCED.value)


@activity.defn
def revert_calendar_sync(inp: CalendarSyncInput) -> None:
    """Compensation for sync_calendar — pushed onto the saga's
    compensation stack right after the forward step succeeds, same as
    every other step (design §7: "revert calendar sync (step 3), release
    slot (step 2), mark appointment failed")."""
    sync_calendar_task.delay(inp.appointment_id, inp.provider_id, CalendarSyncAction.REVERTED.value)


@activity.defn
def billing_precheck(inp: BillingPrecheckInput) -> None:
    """STUBBED — always approves. Structured so a real HTTP call to the
    billing service (currently just a health-check stub itself) drops in
    here later without changing this function's signature, retry policy,
    or the workflow's call site."""
    appointment_id = uuid.UUID(inp.appointment_id)
    with session_scope() as db:
        db.execute(
            update(Appointment)
            .where(
                Appointment.id == appointment_id,
                Appointment.status == AppointmentStatus.RESERVED,
            )
            .values(status=AppointmentStatus.PAYMENT_PENDING)
        )

    approved = True
    if not approved:
        raise ApplicationError("billing_declined", non_retryable=True)


@activity.defn
def confirm_appointment(inp: ConfirmInput) -> ConfirmResult:
    appointment_id = uuid.UUID(inp.appointment_id)
    with session_scope() as db:
        result = db.execute(
            update(Appointment)
            .where(
                Appointment.id == appointment_id,
                Appointment.status == AppointmentStatus.PAYMENT_PENDING,
            )
            .values(status=AppointmentStatus.CONFIRMED)
        )
        if result.rowcount == 0:
            # Already confirmed by a prior attempt of this same activity
            # (Temporal's at-least-once retries) — the event was already
            # published then. Publishing again here would mint a second,
            # differently-IDed event for the same real confirmation, which
            # event_id-based consumer dedup (design §8) can't catch.
            return ConfirmResult(patient_id=None, provider_id=None, scheduled_for_start_time=None)
        appointment = db.get(Appointment, appointment_id)
        publish(
            db,
            Topic.APPOINTMENT_BOOKED,
            {
                "appointment_id": str(appointment.id),
                "patient_id": str(appointment.patient_id),
                "provider_id": str(appointment.provider_id),
                "slot_id": str(appointment.slot_id),
            },
            actor=str(appointment.patient_id),
        )
        start_time = appointment.slot.start_time
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        patient_id = str(appointment.patient_id)
        provider_id = str(appointment.provider_id)

        # Recorded as SCHEDULED right now, in the same transaction as the
        # confirmation — not when ReminderWorkflow actually wakes up
        # later. That workflow's activity transitions this SAME row to
        # SENT/SKIPPED (crud reminder_log.mark_outcome) rather than
        # inserting its own, so GET /reminders shows "scheduled" for the
        # whole gap between booking and the eta actually arriving, not
        # just after the fact.
        reminder_log_crud.record(
            db,
            appointment_id=appointment.id,
            patient_id=appointment.patient_id,
            provider_id=appointment.provider_id,
            appointment_start_time=start_time,
            appointment_status=appointment.status.value,
        )

    # Starting ReminderWorkflow itself is the WORKFLOW's job, not this
    # activity's — see booking_saga.py, which starts it as an
    # ABANDON-policy child right after this activity returns. An activity
    # can't start a Temporal workflow without connecting its own ad-hoc
    # client (the exact pattern already flagged elsewhere in this codebase
    # as a real cost — a fresh connection per call); returning the data
    # the caller needs avoids that here.
    return ConfirmResult(
        patient_id=patient_id, provider_id=provider_id, scheduled_for_start_time=start_time.isoformat()
    )


@activity.defn
def release_slot(inp: ReleaseSlotInput) -> None:
    with session_scope() as db:
        db.execute(
            update(Slot)
            .where(Slot.id == uuid.UUID(inp.slot_id), Slot.status == SlotStatus.RESERVED)
            .values(status=SlotStatus.OPEN)
        )

    cache.invalidate_slots(uuid.UUID(inp.provider_id))


@activity.defn
def mark_appointment_failed(inp: ConfirmInput) -> None:
    with session_scope() as db:
        db.execute(
            update(Appointment)
            .where(
                Appointment.id == uuid.UUID(inp.appointment_id),
                Appointment.status.in_(
                    [
                        AppointmentStatus.PENDING,
                        AppointmentStatus.RESERVED,
                        AppointmentStatus.PAYMENT_PENDING,
                    ]
                ),
            )
            .values(status=AppointmentStatus.FAILED)
        )

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from kafka_shared import Topic
from temporalio import activity

from app.crud import reminder_log as reminder_log_crud
from app.db.session import session_scope
from app.models.appointment import Appointment, AppointmentStatus
from app.models.reminder_log import ReminderStatus
from app.services.events import publish

logger = logging.getLogger(__name__)


@dataclass
class SendReminderInput:
    appointment_id: str
    patient_id: str
    provider_id: str
    scheduled_for_start_time: str


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@activity.defn
def send_reminder(inp: SendReminderInput) -> None:
    """The actual reminder logic, run once ReminderWorkflow's durable sleep
    wakes up — same behavior the old Celery send_reminder_task had (see
    git history), moved here so the wait itself is durable (survives a
    worker crash/restart via Temporal's own event-sourced replay) instead
    of depending on a Celery eta surviving a crash between the DB commit
    that recorded it and the broker call that scheduled it.

    scheduled_for_start_time is the appointment start time THIS workflow
    was started against — compared against the appointment's actual
    current time below. A reschedule starts a brand new ReminderWorkflow
    for the new eta without cancelling the old one (see
    workflows/reminder.py's docstring for why), so an earlier workflow can
    still wake up after the appointment has moved. Rather than let that
    stale wakeup transition the row, it detects the mismatch itself and
    backs off untouched — the workflow whose scheduled_for_start_time
    actually matches is the one that resolves it.

    STUBBED send, like calendar sync — no real email/SMS provider exists
    here, notification's own handler is the stub for that side."""
    appointment_id = uuid.UUID(inp.appointment_id)

    with session_scope() as db:
        appointment = db.get(Appointment, appointment_id)
        if appointment is None:
            logger.info("appointment %s missing, nothing to do", inp.appointment_id)
            return

        current_start = _as_utc(appointment.slot.start_time)
        scheduled_for = _as_utc(datetime.fromisoformat(inp.scheduled_for_start_time))
        if current_start != scheduled_for:
            logger.info(
                "reminder for appointment %s is stale (scheduled for %s, appointment now at %s) — "
                "superseded by a reschedule, a newer workflow owns it",
                inp.appointment_id,
                inp.scheduled_for_start_time,
                current_start.isoformat(),
            )
            return

        if appointment.status != AppointmentStatus.CONFIRMED:
            # Cancelled since this was scheduled — a reminder for a
            # booking that no longer stands would be actively wrong, not
            # just pointless. Transitions the existing row to SKIPPED
            # (not just logged) so this outcome is visible at GET
            # /reminders too, not only in worker logs.
            row = reminder_log_crud.mark_outcome(
                db,
                appointment_id=appointment_id,
                status=ReminderStatus.SKIPPED,
                appointment_status=appointment.status.value,
            )
            if row is None:
                logger.info("reminder outcome already recorded for appointment %s", inp.appointment_id)
                return
            logger.info(
                "skipped reminder for appointment %s, status=%s", inp.appointment_id, appointment.status.value
            )
            return

        row = reminder_log_crud.mark_outcome(
            db,
            appointment_id=appointment.id,
            status=ReminderStatus.SENT,
            appointment_status=appointment.status.value,
        )
        if row is None:
            logger.info("reminder already sent for appointment %s, skipping", inp.appointment_id)
            return

        publish(
            db,
            Topic.REMINDER_SCHEDULED,
            {
                "appointment_id": inp.appointment_id,
                "patient_id": inp.patient_id,
                "provider_id": inp.provider_id,
            },
            actor=inp.patient_id,
        )
    logger.info("reminder scheduled for appointment %s", inp.appointment_id)

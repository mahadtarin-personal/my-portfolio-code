import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.reminder_log import ReminderLog, ReminderStatus


def record(
    db: Session,
    *,
    appointment_id: uuid.UUID,
    patient_id: uuid.UUID,
    provider_id: uuid.UUID,
    appointment_start_time: datetime,
    appointment_status: str,
) -> ReminderLog | None:
    """Called once, at scheduling time (confirm_appointment) — creates the
    row as SCHEDULED. Returns None (not an error) if this appointment
    already has a row — the unique constraint is the actual dedup
    mechanism, same pattern as calendar_sync_log.record()."""
    log = ReminderLog(
        appointment_id=appointment_id,
        patient_id=patient_id,
        provider_id=provider_id,
        appointment_start_time=appointment_start_time,
        status=ReminderStatus.SCHEDULED,
        appointment_status=appointment_status,
    )
    db.add(log)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return log


def mark_outcome(
    db: Session, *, appointment_id: uuid.UUID, status: ReminderStatus, appointment_status: str
) -> ReminderLog | None:
    """Called at eta time (send_reminder_task) — transitions the existing
    row to SENT or SKIPPED, from either SCHEDULED (never rescheduled) or
    RESCHEDULED (moved at least once, this is the task that matches its
    current time). The WHERE guard is what makes this safe under Celery's
    own at-least-once retry (same conditional-UPDATE idempotency shape as
    reserve_slot/confirm_appointment elsewhere in this codebase): a second
    delivery of the same task finds the row already past both those
    states and no-ops instead of re-transitioning or double-publishing."""
    result = db.execute(
        update(ReminderLog)
        .where(
            ReminderLog.appointment_id == appointment_id,
            ReminderLog.status.in_([ReminderStatus.SCHEDULED, ReminderStatus.RESCHEDULED]),
        )
        .values(status=status, appointment_status=appointment_status, updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount == 0:
        return None
    return db.scalar(select(ReminderLog).where(ReminderLog.appointment_id == appointment_id))


def reschedule(
    db: Session, *, appointment_id: uuid.UUID, appointment_start_time: datetime
) -> ReminderLog | None:
    """Called from swap_appointment_slot — unconditionally moves the
    existing row to RESCHEDULED with the new appointment time, whatever
    its current status was. No status guard needed here: the caller's own
    top-level idempotency check (appointment.slot_id already == new_slot_id
    -> early return) is what prevents this from running twice for the
    same reschedule, so by the time this executes it's guaranteed to be a
    genuine, one-time transition. Returns None if no row exists yet (the
    reminder was never scheduled for this appointment in the first place —
    the caller then simply doesn't schedule a fresh one either)."""
    result = db.execute(
        update(ReminderLog)
        .where(ReminderLog.appointment_id == appointment_id)
        .values(
            status=ReminderStatus.RESCHEDULED,
            appointment_start_time=appointment_start_time,
            appointment_status="confirmed",
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount == 0:
        return None
    return db.scalar(select(ReminderLog).where(ReminderLog.appointment_id == appointment_id))


def list_recent(
    db: Session, *, appointment_id: uuid.UUID | None = None, limit: int = 50
) -> list[ReminderLog]:
    stmt = select(ReminderLog).order_by(ReminderLog.created_at.desc()).limit(limit)
    if appointment_id is not None:
        stmt = stmt.where(ReminderLog.appointment_id == appointment_id)
    return list(db.scalars(stmt))

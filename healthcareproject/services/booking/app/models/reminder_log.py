import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReminderStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    SKIPPED = "skipped"
    RESCHEDULED = "rescheduled"


class ReminderLog(Base):
    """STUBBED send — notification already has a handler for
    reminder.scheduled (message text: "Reminder: you have an upcoming
    appointment"); this table is booking's own record of the reminder's
    full lifecycle, visible at this service's own host (GET /reminders)
    without cross-referencing notification or reading worker logs.

    One row per appointment, created SCHEDULED the moment confirm_appointment
    computes the reminder's eta (app/activities/booking.py) — not when
    Celery actually runs it later. send_reminder_task (app/tasks/reminder.py)
    then transitions that SAME row to SENT (still CONFIRMED when the eta
    arrived) or SKIPPED (cancelled by then) — never inserts a second row.
    appointment_status is the appointment's own status at the moment of
    that transition (e.g. "confirmed" alongside SENT, "cancelled" alongside
    SKIPPED) — status says what the reminder did, this says why.

    RESCHEDULED is different from the other two outcomes: it's not
    terminal. crud.reminder_log.reschedule() (called from
    swap_appointment_slot) moves this SAME row back to RESCHEDULED with
    the new appointment_start_time, and a fresh Celery task gets scheduled
    for the new eta — mark_outcome() accepts transitioning from either
    SCHEDULED or RESCHEDULED into SENT/SKIPPED, so whichever task actually
    matches the appointment's current time is the one that resolves it.
    An earlier, now-stale task (still holding the pre-reschedule eta)
    detects the mismatch itself and backs off without touching the row —
    see send_reminder_task's staleness check."""

    __tablename__ = "reminder_log"
    __table_args__ = (UniqueConstraint("appointment_id", name="uq_reminder_log_appointment_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("appointments.id"), index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # The appointment's own start time — captured once, at scheduling
    # time, so GET /reminders can show "reminder for an appointment at X"
    # without a caller having to cross-reference /appointments or /slots
    # themselves. Not re-read at SENT/SKIPPED time since it doesn't
    # change after booking (reschedule is a different appointment_id).
    appointment_start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[ReminderStatus] = mapped_column(Enum(ReminderStatus, name="reminder_status"))
    appointment_status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

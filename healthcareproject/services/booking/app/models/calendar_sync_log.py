import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CalendarSyncAction(str, enum.Enum):
    SYNCED = "synced"
    REVERTED = "reverted"
    RESCHEDULED = "rescheduled"


class CalendarSyncLog(Base):
    """STUBBED by default — most environments running this project have no
    Google Calendar OAuth credentials, so this table normally just stands
    in for "the provider's calendar was actually pushed to" the same way
    billing_precheck stands in for a real payment gateway call. When
    GOOGLE_CALENDAR_ENABLED=true and real OAuth credentials are configured
    (app/services/google_calendar.py), rows are backed by an actual event
    on a real calendar — see external_event_id below.

    One row per (appointment_id, action) for SYNCED/REVERTED — the
    partial unique index below (deliberately excluding RESCHEDULED, same
    postgresql_where/sqlite_where pattern as Appointment's own active-slot
    index) is what makes the Celery task safe to run twice for either of
    those. The Temporal activity that enqueues it
    (app/activities/booking.py::sync_calendar / revert_calendar_sync) can
    retry at-least-once same as every other saga step; a duplicate
    enqueue just hits the index and no-ops, same idempotency shape as
    everywhere else in this project (design §8).

    RESCHEDULED is exempt from that uniqueness on purpose — a single
    appointment can legitimately be rescheduled more than once, and each
    one is its own row (a real, repeatable event, not a once-per-appointment
    outcome). Its own retry-safety instead comes from the caller:
    swap_appointment_slot only ever reaches the point where it enqueues
    this once per genuine reschedule (its own idempotency check returns
    early on a Temporal retry, before re-enqueueing)."""

    __tablename__ = "calendar_sync_log"
    __table_args__ = (
        Index(
            "uq_calendar_sync_log_appointment_action",
            "appointment_id",
            "action",
            unique=True,
            postgresql_where=text("action != 'RESCHEDULED'"),
            sqlite_where=text("action != 'RESCHEDULED'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("appointments.id"), index=True
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    action: Mapped[CalendarSyncAction] = mapped_column(
        Enum(CalendarSyncAction, name="calendar_sync_action")
    )
    # Google's own event id, set only when google_calendar_enabled is on
    # and this row is a real SYNCED push — a later REVERTED action looks
    # this up (via the SYNCED row for the same appointment) to know
    # exactly which real event to delete. Null for stub-mode rows.
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

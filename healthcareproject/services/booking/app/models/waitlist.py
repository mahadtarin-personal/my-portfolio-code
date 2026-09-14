import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WaitlistStatus(str, enum.Enum):
    WAITING = "waiting"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class WaitlistEntry(Base):
    """A patient waiting for one specific already-taken slot (not a general
    provider/timeframe queue). Unique on (patient_id, slot_id) among active
    (WAITING) entries only — same partial-unique-index pattern as
    appointments.slot_id, so a fulfilled/cancelled entry doesn't block a
    patient from joining again later."""

    __tablename__ = "waitlist_entries"
    __table_args__ = (
        Index(
            "uq_waitlist_patient_slot_active",
            "patient_id",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'WAITING'"),
            sqlite_where=text("status = 'WAITING'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    slot_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    status: Mapped[WaitlistStatus] = mapped_column(
        Enum(WaitlistStatus, name="waitlist_status"), default=WaitlistStatus.WAITING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

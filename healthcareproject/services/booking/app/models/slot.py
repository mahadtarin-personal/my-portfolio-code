import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, UniqueConstraint, Uuid, and_
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.appointment import Appointment, AppointmentStatus


class SlotStatus(str, enum.Enum):
    OPEN = "open"
    RESERVED = "reserved"
    BLOCKED = "blocked"


class Slot(Base):
    """provider_id has no FK constraint — Profiles owns the Provider row in
    a separate database (service-per-database, no cross-service foreign
    keys, per deploy/postgres/README.md).

    Unique on (provider_id, start_time): a provider can't have two
    different slots starting at the same instant, and this is what makes
    repeated/concurrent slot generation safe to re-run."""

    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("provider_id", "start_time", name="uq_slots_provider_start"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus, name="slot_status"), default=SlotStatus.OPEN
    )

    # Plain FK-based matching (just Slot.id == Appointment.slot_id) isn't
    # enough — the DB explicitly allows multiple appointment rows to share
    # a slot_id over time (uq_appointments_slot_id_active only enforces
    # uniqueness among ACTIVE statuses, so a cancelled row and a later
    # active one legitimately coexist). Without this extra filter,
    # uselist=False has nothing telling it which of those rows to prefer —
    # confirmed live: SQLAlchemy silently picked the stale CANCELLED row
    # over the current CONFIRMED one (with only an SAWarning, no error),
    # which broke reserve_slot's retry-disambiguation check (it compares
    # slot.appointment.id against the appointment being reserved). The
    # primaryjoin makes "the current appointment holding this slot" mean
    # what it always should have: the one active row, ignoring history.
    appointment: Mapped["Appointment | None"] = relationship(
        primaryjoin=lambda: and_(
            Slot.id == Appointment.slot_id,
            Appointment.status.not_in([AppointmentStatus.CANCELLED, AppointmentStatus.FAILED]),
        ),
        back_populates="slot",
        uselist=False,
        viewonly=True,
    )

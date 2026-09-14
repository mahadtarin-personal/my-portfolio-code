import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.slot import Slot
    from app.models.visit import Visit


class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"
    RESERVED = "reserved"
    PAYMENT_PENDING = "payment_pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class Appointment(Base):
    """patient_id/provider_id are references into Profiles' database, not
    real foreign keys — same service-per-database boundary as Slot.

    slot_id is unique only among active appointments (see __table_args__),
    not table-wide — otherwise a cancelled/failed appointment would
    permanently block anyone from ever booking that slot again."""

    __tablename__ = "appointments"
    __table_args__ = (
        # Postgres enums store the Python Enum member's .name (uppercase),
        # not .value — matching the original migration's
        # sa.Enum('CONFIRMED', 'CANCELLED', 'COMPLETED', ...).
        Index(
            "uq_appointments_slot_id_active",
            "slot_id",
            unique=True,
            postgresql_where=text("status NOT IN ('CANCELLED', 'FAILED')"),
            sqlite_where=text("status NOT IN ('CANCELLED', 'FAILED')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    slot_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("slots.id"))
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status"), default=AppointmentStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    slot: Mapped["Slot"] = relationship(back_populates="appointment")
    visit: Mapped["Visit | None"] = relationship(back_populates="appointment", uselist=False)

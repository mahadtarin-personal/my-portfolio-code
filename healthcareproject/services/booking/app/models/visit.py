import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment


class VisitStatus(str, enum.Enum):
    CHECKED_IN = "checked_in"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Visit(Base):
    """1:1 with a CONFIRMED Appointment — mirrors the Slot<->Appointment
    pattern (no Visit row means "not checked in yet," no sentinel enum
    member needed). Plain state machine, not a Temporal workflow: a single
    local transition per hop, nothing else to compensate today (design §6
    doesn't describe visit completion as a saga the way booking is)."""

    __tablename__ = "visits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("appointments.id"), unique=True
    )
    status: Mapped[VisitStatus] = mapped_column(Enum(VisitStatus, name="visit_status"))
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    appointment: Mapped["Appointment"] = relationship(back_populates="visit")

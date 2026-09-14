import enum
import uuid
from datetime import date, time
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Time, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.provider import Provider


class DayOfWeek(int, enum.Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class TimeOffSource(str, enum.Enum):
    MANUAL = "manual"
    EXTERNAL_CALENDAR = "external_calendar"


class ProviderSchedule(Base):
    """Recurring weekly template — e.g. Mon-Fri 9am-5pm in 20-min slots.
    `time_off` (below) carves out exceptions; a background job (Phase 2)
    expands both into bookable Slot rows over in the booking service."""

    __tablename__ = "provider_schedule"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("providers.id"))
    day_of_week: Mapped[DayOfWeek] = mapped_column(Enum(DayOfWeek, name="day_of_week"))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    slot_duration_min: Mapped[int] = mapped_column(Integer)

    provider: Mapped["Provider"] = relationship(back_populates="schedules")


class TimeOff(Base):
    """Unique on (provider_id, start_date, end_date) — the exact-duplicate
    resubmission case (same provider, same range, submitted more than
    once), not general overlap detection between different ranges."""

    __tablename__ = "time_off"
    __table_args__ = (
        UniqueConstraint("provider_id", "start_date", "end_date", name="uq_time_off_provider_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("providers.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[TimeOffSource] = mapped_column(
        Enum(TimeOffSource, name="time_off_source"), default=TimeOffSource.MANUAL
    )

    provider: Mapped["Provider"] = relationship(back_populates="time_off_periods")

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.clinic import Clinic
    from app.models.schedule import ProviderSchedule, TimeOff


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clinics.id"))
    name: Mapped[str] = mapped_column(String(255))
    specialty: Mapped[str] = mapped_column(String(255))
    license_number: Mapped[str] = mapped_column(String(100), unique=True)
    consultation_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    contact_email: Mapped[str] = mapped_column(String(255))
    contact_phone: Mapped[str] = mapped_column(String(32))

    clinic: Mapped["Clinic"] = relationship(back_populates="providers")
    schedules: Mapped[list["ProviderSchedule"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    time_off_periods: Mapped[list["TimeOff"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )

import uuid
from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import String, Time, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.provider import Provider


class Clinic(Base):
    __tablename__ = "clinics"
    __table_args__ = (UniqueConstraint("name", "address", name="uq_clinics_name_address"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(500))
    open_time: Mapped[time] = mapped_column(Time)
    close_time: Mapped[time] = mapped_column(Time)

    providers: Mapped[list["Provider"]] = relationship(back_populates="clinic")

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IdempotencyKey(Base):
    """Backs the Idempotency-Key header on POST /appointments (design §8).
    A durable (patient_id, key) -> appointment_id mapping, not a cached
    response body — the live Appointment row is always re-read, so a
    replayed request naturally reflects whatever state the saga has reached
    by the time of the retry."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("patient_id", "key", name="uq_idempotency_patient_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    key: Mapped[str] = mapped_column(String(255))
    appointment_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc) + timedelta(hours=24)
    )

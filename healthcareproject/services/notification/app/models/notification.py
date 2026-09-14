import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"


class NotificationStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"


class Notification(Base):
    """One row per Kafka event this service reacted to. Unique on
    event_id — that IS the dedup mechanism design §8 calls for ("Kafka
    consumers dedupe by the event's own unique ID, set at publish time"):
    if the same event gets redelivered (Kafka's own at-least-once
    guarantee, or a consumer crash before the offset commits), the unique
    constraint rejects the second insert instead of double-sending."""

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("event_id", name="uq_notifications_event_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    recipient: Mapped[str] = mapped_column(String(255))
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel")
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status")
    )
    message: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

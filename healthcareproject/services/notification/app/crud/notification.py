import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationChannel, NotificationStatus


def already_processed(db: Session, event_id: str) -> bool:
    return db.scalar(select(Notification).where(Notification.event_id == event_id)) is not None


def record(
    db: Session,
    *,
    event_id: str,
    event_type: str,
    recipient: str,
    channel: NotificationChannel,
    status: NotificationStatus,
    message: str,
) -> Notification | None:
    """Returns None (not an error) if event_id already exists — the
    unique constraint is the actual source of truth for dedup; this just
    catches the resulting IntegrityError cleanly under a race between two
    redelivered copies of the same event."""
    notification = Notification(
        id=uuid.uuid4(),
        event_id=event_id,
        event_type=event_type,
        recipient=recipient,
        channel=channel,
        status=status,
        message=message,
    )
    db.add(notification)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return notification


def list_recent(db: Session, limit: int = 50) -> list[Notification]:
    return list(
        db.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(limit))
    )

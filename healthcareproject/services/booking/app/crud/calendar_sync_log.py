import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.calendar_sync_log import CalendarSyncAction, CalendarSyncLog


def get(db: Session, *, appointment_id: uuid.UUID, action: CalendarSyncAction) -> CalendarSyncLog | None:
    return db.scalar(
        select(CalendarSyncLog).where(
            CalendarSyncLog.appointment_id == appointment_id, CalendarSyncLog.action == action
        )
    )


def record(
    db: Session,
    *,
    appointment_id: uuid.UUID,
    provider_id: uuid.UUID,
    action: CalendarSyncAction,
    external_event_id: str | None = None,
) -> CalendarSyncLog | None:
    """Returns None (not an error) if this (appointment_id, action) pair
    was already recorded — the unique constraint is the actual dedup
    mechanism, same pattern as idempotency.claim()."""
    log = CalendarSyncLog(
        appointment_id=appointment_id,
        provider_id=provider_id,
        action=action,
        external_event_id=external_event_id,
    )
    db.add(log)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return log


def list_recent(
    db: Session, *, appointment_id: uuid.UUID | None = None, limit: int = 50
) -> list[CalendarSyncLog]:
    stmt = select(CalendarSyncLog).order_by(CalendarSyncLog.created_at.desc()).limit(limit)
    if appointment_id is not None:
        stmt = stmt.where(CalendarSyncLog.appointment_id == appointment_id)
    return list(db.scalars(stmt))

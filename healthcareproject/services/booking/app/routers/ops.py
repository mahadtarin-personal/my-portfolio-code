import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.db.session import get_db
from app.schemas.ops import CalendarSyncLogRead, ReminderLogRead

router = APIRouter(tags=["ops"])


@router.get("/calendar-sync-log", response_model=list[CalendarSyncLogRead])
def list_calendar_sync_log(
    appointment_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[CalendarSyncLogRead]:
    """No auth — a verification/debugging surface, same precedent as
    notification's GET /notifications and audit's GET /audit. Shows
    saga step 3's actual effect: SYNCED on a normal confirm, REVERTED
    too if billing later declined and the saga compensated."""
    rows = crud.calendar_sync_log.list_recent(db, appointment_id=appointment_id)
    return [CalendarSyncLogRead.model_validate(r) for r in rows]


@router.get("/reminders", response_model=list[ReminderLogRead])
def list_reminders(
    appointment_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[ReminderLogRead]:
    """No auth, same precedent as list_calendar_sync_log above. One row
    per appointment a reminder has actually fired for — check
    notification's GET /notifications for the reminder.scheduled event
    this produces downstream."""
    rows = crud.reminder_log.list_recent(db, appointment_id=appointment_id)
    return [ReminderLogRead.model_validate(r) for r in rows]

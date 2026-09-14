import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.slot import Slot, SlotStatus


def get(db: Session, slot_id: uuid.UUID) -> Slot | None:
    return db.get(Slot, slot_id)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def list_open(db: Session, *, provider_id: uuid.UUID | None = None) -> list[Slot]:
    """status=OPEN alone isn't enough — a slot nobody ever booked stays
    OPEN forever once its start_time passes (nothing transitions it out),
    so without a time filter here, "available slots" would keep showing
    yesterday's/last month's never-booked slots as if they were still
    bookable. Filtered in Python rather than in the WHERE clause: SQLite
    (tests) round-trips DateTime(timezone=True) values as naive, so an
    aware `now` bound directly into SQL risks the exact cross-dialect
    string-comparison mismatch this codebase already works around
    elsewhere (see services/slot_generation.py's own _as_utc)."""
    stmt = select(Slot).where(Slot.status == SlotStatus.OPEN)
    if provider_id is not None:
        stmt = stmt.where(Slot.provider_id == provider_id)
    now = datetime.now(timezone.utc)
    return [s for s in db.scalars(stmt) if _as_utc(s.start_time) >= now]


def create(
    db: Session, *, provider_id: uuid.UUID, start_time: datetime, end_time: datetime
) -> Slot:
    """No HTTP route exposes this yet — slot generation is the Phase 2/3
    recurring job (design §5.1) that expands provider_schedule + time_off.
    This exists so tests and future wiring have something to call."""
    slot = Slot(
        id=uuid.uuid4(),
        provider_id=provider_id,
        start_time=start_time,
        end_time=end_time,
        status=SlotStatus.OPEN,
    )
    db.add(slot)
    db.flush()
    return slot

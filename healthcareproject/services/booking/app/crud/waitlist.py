import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.waitlist import WaitlistEntry, WaitlistStatus


def join(
    db: Session, *, patient_id: uuid.UUID, provider_id: uuid.UUID, slot_id: uuid.UUID
) -> WaitlistEntry:
    entry = WaitlistEntry(
        id=uuid.uuid4(),
        patient_id=patient_id,
        provider_id=provider_id,
        slot_id=slot_id,
        status=WaitlistStatus.WAITING,
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("already_waiting_for_this_slot") from exc
    return entry


def find_next_waiting(db: Session, slot_id: uuid.UUID) -> WaitlistEntry | None:
    """Oldest WAITING entry for this slot — FIFO."""
    return db.scalar(
        select(WaitlistEntry)
        .where(WaitlistEntry.slot_id == slot_id, WaitlistEntry.status == WaitlistStatus.WAITING)
        .order_by(WaitlistEntry.created_at)
    )


def mark_fulfilled(db: Session, entry: WaitlistEntry) -> WaitlistEntry:
    entry.status = WaitlistStatus.FULFILLED
    db.flush()
    return entry


def list_for_slot(db: Session, slot_id: uuid.UUID) -> list[WaitlistEntry]:
    return list(
        db.scalars(
            select(WaitlistEntry)
            .where(WaitlistEntry.slot_id == slot_id)
            .order_by(WaitlistEntry.created_at)
        )
    )


def list_for_patient(db: Session, patient_id: uuid.UUID) -> list[WaitlistEntry]:
    return list(
        db.scalars(
            select(WaitlistEntry)
            .where(WaitlistEntry.patient_id == patient_id)
            .order_by(WaitlistEntry.created_at.desc())
        )
    )

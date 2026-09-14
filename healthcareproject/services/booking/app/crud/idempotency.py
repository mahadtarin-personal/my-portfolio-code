import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency_key import IdempotencyKey


def find_active(db: Session, *, patient_id: uuid.UUID, key: str) -> IdempotencyKey | None:
    stmt = select(IdempotencyKey).where(
        IdempotencyKey.patient_id == patient_id,
        IdempotencyKey.key == key,
        IdempotencyKey.expires_at > datetime.now(timezone.utc),
    )
    return db.scalars(stmt).first()


def claim(
    db: Session, *, patient_id: uuid.UUID, key: str, appointment_id: uuid.UUID
) -> IdempotencyKey | None:
    """Try to durably own (patient_id, key) -> appointment_id.

    Returns None if this request won the race (caller proceeds to start the
    workflow for `appointment_id`). Returns the pre-existing row if another
    request already claimed this key first (caller should use that row's
    appointment_id instead, and discard its own not-yet-committed appointment).
    """
    db.add(IdempotencyKey(patient_id=patient_id, key=key, appointment_id=appointment_id))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return find_active(db, patient_id=patient_id, key=key)
    return None

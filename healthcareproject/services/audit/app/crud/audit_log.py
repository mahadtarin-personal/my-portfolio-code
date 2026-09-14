from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.services.hash_chain import GENESIS_HASH, compute_hash


def already_processed(db: Session, event_id: str) -> bool:
    return db.scalar(select(AuditLog).where(AuditLog.event_id == event_id)) is not None


def _last_row(db: Session) -> AuditLog | None:
    return db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))


def append(
    db: Session, *, event_id: str, event_type: str, actor: str | None, payload: dict
) -> AuditLog | None:
    """Returns None (not an error) if event_id already exists — same
    dedup contract as notification's crud.record(). Single-writer only:
    this project runs exactly one audit-worker replica, so there's no
    concurrent-append race to guard against here (a real multi-writer
    deployment would need the prev_hash lookup + insert to happen inside
    a serializable transaction or use a DB-level advisory lock)."""
    last = _last_row(db)
    prev_hash = last.hash if last is not None else GENESIS_HASH
    created_at = datetime.now(timezone.utc)
    row = AuditLog(
        event_id=event_id,
        event_type=event_type,
        actor=actor,
        payload=payload,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, event_type, actor, payload, created_at),
        created_at=created_at,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return row


def list_recent(db: Session, limit: int = 50) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)))


def verify_chain(db: Session) -> tuple[bool, int | None, int]:
    """Recomputes every row's hash from its own fields + the previous
    row's *stored* hash, and compares. This is the independent,
    code-level second layer design §13 describes ("a nightly Celery job
    still verifies the chain... a mismatch pages") — separate from the
    DB-level INSERT-only grant, which prevents tampering rather than
    detecting it. Returns (valid, first_broken_id_or_None, rows_checked)."""
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    prev_hash = GENESIS_HASH
    for row in rows:
        expected = compute_hash(prev_hash, row.event_type, row.actor, row.payload, row.created_at)
        if row.prev_hash != prev_hash or row.hash != expected:
            return False, row.id, len(rows)
        prev_hash = row.hash
    return True, None, len(rows)

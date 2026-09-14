from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.visit import Visit, VisitStatus


def check_in(db: Session, appointment: Appointment) -> Visit:
    if appointment.status != AppointmentStatus.CONFIRMED:
        raise ValueError("appointment_not_confirmed")
    if appointment.visit is not None:
        raise ValueError("already_checked_in")
    visit = Visit(
        appointment_id=appointment.id,
        status=VisitStatus.CHECKED_IN,
        checked_in_at=datetime.now(timezone.utc),
    )
    db.add(visit)
    db.flush()
    return visit


def start(db: Session, visit: Visit) -> Visit:
    if visit.status != VisitStatus.CHECKED_IN:
        raise ValueError("invalid_transition")
    visit.status = VisitStatus.IN_PROGRESS
    visit.started_at = datetime.now(timezone.utc)
    db.flush()
    return visit


def complete(db: Session, visit: Visit) -> Visit:
    if visit.status != VisitStatus.IN_PROGRESS:
        raise ValueError("invalid_transition")
    visit.status = VisitStatus.COMPLETED
    visit.completed_at = datetime.now(timezone.utc)
    visit.appointment.status = AppointmentStatus.COMPLETED
    db.flush()
    return visit

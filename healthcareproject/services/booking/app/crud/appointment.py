import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.slot import SlotStatus


def get(db: Session, appointment_id: uuid.UUID) -> Appointment | None:
    return db.get(Appointment, appointment_id)


def list_for_patient(db: Session, patient_id: uuid.UUID) -> list[Appointment]:
    return list(
        db.scalars(
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.created_at.desc())
        )
    )


def list_for_provider(db: Session, provider_id: uuid.UUID) -> list[Appointment]:
    return list(
        db.scalars(
            select(Appointment)
            .where(Appointment.provider_id == provider_id)
            .order_by(Appointment.created_at.desc())
        )
    )


def get_confirmed_for_patient_and_provider(
    db: Session, patient_id: uuid.UUID, provider_id: uuid.UUID
) -> Appointment | None:
    """Used by waitlist promotion: if a promoted patient already holds a
    confirmed appointment with this provider, promotion should shift that
    appointment onto the freed slot rather than double-booking them."""
    return db.scalar(
        select(Appointment).where(
            Appointment.patient_id == patient_id,
            Appointment.provider_id == provider_id,
            Appointment.status == AppointmentStatus.CONFIRMED,
        )
    )


def create_pending(
    db: Session,
    *,
    appointment_id: uuid.UUID,
    patient_id: uuid.UUID,
    provider_id: uuid.UUID,
    slot_id: uuid.UUID,
) -> Appointment:
    """Creates the Appointment row only, at PENDING — never touches the
    slot. This is what POST /appointments does synchronously, so the client
    gets an id to poll immediately; the booking saga (app/workflows) does
    the actual slot reservation, billing pre-check, and confirmation as a
    Temporal workflow (design §5.2)."""
    appointment = Appointment(
        id=appointment_id,
        patient_id=patient_id,
        provider_id=provider_id,
        slot_id=slot_id,
        status=AppointmentStatus.PENDING,
    )
    db.add(appointment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("slot_unavailable") from exc
    return appointment


CANCELLABLE_STATUSES = {
    AppointmentStatus.PENDING,
    AppointmentStatus.RESERVED,
    AppointmentStatus.PAYMENT_PENDING,
    AppointmentStatus.CONFIRMED,
}


def cancel(db: Session, appointment: Appointment) -> Appointment:
    """Raises ValueError if the appointment is already in a terminal state
    (CANCELLED/COMPLETED/FAILED) — without this, re-cancelling an already-
    cancelled appointment would force its slot_id back to OPEN even if
    that slot has since been rebooked by someone else entirely, silently
    corrupting a different patient's active booking."""
    if appointment.status not in CANCELLABLE_STATUSES:
        raise ValueError("invalid_transition")
    appointment.status = AppointmentStatus.CANCELLED
    if appointment.slot is not None:
        appointment.slot.status = SlotStatus.OPEN
    db.flush()
    return appointment

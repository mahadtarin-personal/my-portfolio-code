from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from app import crud
from app.models.appointment import Appointment


class PromotionAction(str, Enum):
    SHIFT_EXISTING = "shift_existing"
    FRESH_BOOKING = "fresh_booking"


@dataclass
class PromotionResult:
    action: PromotionAction
    patient_id: uuid.UUID
    provider_id: uuid.UUID
    slot_id: uuid.UUID
    appointment: Appointment


def promote_next_waitlisted(
    db: Session, provider_id: uuid.UUID, freed_slot_id: uuid.UUID
) -> PromotionResult | None:
    """Pure DB logic, no I/O — deciding *what* should happen next for a
    freed slot. Starting the actual workflow (reschedule vs fresh booking)
    is async I/O and is the caller's job, same split used for slot
    generation. Returns None if nobody is waiting (a no-op, not an error).

    If the promoted patient already holds a confirmed appointment with this
    same provider, that appointment should be *shifted* onto the freed slot
    rather than double-booking them — this also cascades: shifting them off
    their old slot frees it too, re-triggering promotion for anyone waiting
    on that one."""
    entry = crud.waitlist.find_next_waiting(db, freed_slot_id)
    if entry is None:
        return None

    existing = crud.appointment.get_confirmed_for_patient_and_provider(
        db, entry.patient_id, provider_id
    )
    crud.waitlist.mark_fulfilled(db, entry)

    if existing is not None:
        return PromotionResult(
            action=PromotionAction.SHIFT_EXISTING,
            patient_id=entry.patient_id,
            provider_id=provider_id,
            slot_id=freed_slot_id,
            appointment=existing,
        )

    new_appointment = crud.appointment.create_pending(
        db,
        appointment_id=uuid.uuid4(),
        patient_id=entry.patient_id,
        provider_id=provider_id,
        slot_id=freed_slot_id,
    )
    return PromotionResult(
        action=PromotionAction.FRESH_BOOKING,
        patient_id=entry.patient_id,
        provider_id=provider_id,
        slot_id=freed_slot_id,
        appointment=new_appointment,
    )

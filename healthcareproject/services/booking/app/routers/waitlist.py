import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from jwt_shared import Role, TokenPayload
from sqlalchemy.orm import Session

from app import crud
from app.db.session import get_db
from app.deps import auth
from app.models.slot import SlotStatus
from app.schemas.waitlist import WaitlistEntryRead, WaitlistJoin

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


def _ensure_owner_or_staff(token: TokenPayload, patient_id: uuid.UUID) -> None:
    if token.role == Role.PATIENT.value and token.sub != str(patient_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this resource")


@router.post(
    "",
    response_model=WaitlistEntryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_roles(Role.PATIENT))],
)
def join_waitlist(
    payload: WaitlistJoin,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> WaitlistEntryRead:
    slot = crud.slot.get(db, payload.slot_id)
    if slot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slot not found")
    if slot.status == SlotStatus.OPEN:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This slot is open — book it directly instead of waiting"
        )

    patient_id = uuid.UUID(token.sub)
    try:
        entry = crud.waitlist.join(
            db, patient_id=patient_id, provider_id=slot.provider_id, slot_id=slot.id
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Already on the waitlist for this slot"
        ) from exc
    db.commit()
    return WaitlistEntryRead.model_validate(entry)


@router.get("", response_model=list[WaitlistEntryRead])
def list_waitlist(
    slot_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> list[WaitlistEntryRead]:
    """Filter by slot_id (existing behavior, any authenticated role — for
    test visibility) or by patient_id (a patient's own waitlist entries,
    ownership-checked — the "am I in queue" view)."""
    if patient_id is not None:
        _ensure_owner_or_staff(token, patient_id)
        return [WaitlistEntryRead.model_validate(e) for e in crud.waitlist.list_for_patient(db, patient_id)]
    if slot_id is not None:
        return [WaitlistEntryRead.model_validate(e) for e in crud.waitlist.list_for_slot(db, slot_id)]
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide slot_id or patient_id")

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from jwt_shared import Role, TokenPayload
from kafka_shared import Topic
from sqlalchemy.orm import Session

from app import crud
from app.db.session import get_db
from app.deps import auth, ensure_self_or_roles
from app.schemas.patient import PatientRead, PatientRegister
from app.services.events import publish

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def register_patient(payload: PatientRegister, db: Session = Depends(get_db)) -> PatientRead:
    if crud.user.get_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    patient = crud.patient.create(db, payload)
    crud.user.create(
        db,
        email=payload.email,
        password=payload.password,
        role=Role.PATIENT,
        patient_id=patient.id,
    )
    # Always "self" today — there's no staff-driven patient-registration
    # path in this codebase yet, only this one public self-registration
    # endpoint. The field exists so that path can set it correctly later
    # without changing the event shape.
    publish(
        db,
        Topic.PATIENT_REGISTERED,
        {"patient_id": str(patient.id), "registered_by": "self"},
        actor=str(patient.id),
    )
    db.commit()  # patient + user + outbox row all commit together
    return PatientRead.model_validate(patient)


@router.get("/{patient_id}", response_model=PatientRead)
def get_patient(
    patient_id: uuid.UUID,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> PatientRead:
    ensure_self_or_roles(token, patient_id, Role.ADMIN, Role.FRONT_DESK)
    patient = crud.patient.get(db, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    return PatientRead.model_validate(patient)

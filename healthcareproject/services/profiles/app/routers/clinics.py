import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from jwt_shared import Role
from sqlalchemy.orm import Session

from app import crud
from app.db.session import get_db
from app.deps import auth
from app.schemas.clinic import ClinicCreate, ClinicRead

router = APIRouter(prefix="/clinics", tags=["clinics"])


@router.post(
    "",
    response_model=ClinicRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_roles(Role.ADMIN))],
)
def create_clinic(payload: ClinicCreate, db: Session = Depends(get_db)) -> ClinicRead:
    try:
        clinic = crud.clinic.create(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A clinic with this name and address already exists"
        ) from exc
    db.commit()
    return ClinicRead.model_validate(clinic)


@router.get("", response_model=list[ClinicRead])
def list_clinics(db: Session = Depends(get_db)) -> list[ClinicRead]:
    return [ClinicRead.model_validate(c) for c in crud.clinic.list_all(db)]


@router.get("/{clinic_id}", response_model=ClinicRead)
def get_clinic(clinic_id: uuid.UUID, db: Session = Depends(get_db)) -> ClinicRead:
    clinic = crud.clinic.get(db, clinic_id)
    if clinic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found")
    return ClinicRead.model_validate(clinic)

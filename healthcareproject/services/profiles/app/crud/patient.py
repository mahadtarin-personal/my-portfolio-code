import uuid

from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.schemas.patient import PatientRegister


def get(db: Session, patient_id: uuid.UUID) -> Patient | None:
    return db.get(Patient, patient_id)


def create(db: Session, data: PatientRegister) -> Patient:
    patient = Patient(id=uuid.uuid4(), name=data.name, email=data.email, phone=data.phone)
    db.add(patient)
    db.flush()
    return patient

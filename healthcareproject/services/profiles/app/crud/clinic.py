import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinic import Clinic
from app.schemas.clinic import ClinicCreate


def get(db: Session, clinic_id: uuid.UUID) -> Clinic | None:
    return db.get(Clinic, clinic_id)


def list_all(db: Session) -> list[Clinic]:
    return list(db.scalars(select(Clinic)))


def get_by_name_and_address(db: Session, name: str, address: str) -> Clinic | None:
    return db.scalar(select(Clinic).where(Clinic.name == name, Clinic.address == address))


def create(db: Session, data: ClinicCreate) -> Clinic:
    if get_by_name_and_address(db, data.name, data.address) is not None:
        raise ValueError("clinic_already_exists")

    clinic = Clinic(
        id=uuid.uuid4(),
        name=data.name,
        address=data.address,
        open_time=data.open_time,
        close_time=data.close_time,
    )
    db.add(clinic)
    db.flush()
    return clinic

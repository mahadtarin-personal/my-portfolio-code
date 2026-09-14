import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.provider import Provider
from app.models.schedule import ProviderSchedule, TimeOff, TimeOffSource
from app.schemas.provider import ProviderRegister
from app.schemas.schedule import ProviderScheduleEntry, TimeOffCreate


def get(db: Session, provider_id: uuid.UUID) -> Provider | None:
    return db.get(Provider, provider_id)


def list_all(db: Session) -> list[Provider]:
    return list(db.scalars(select(Provider)))


def get_by_license_number(db: Session, license_number: str) -> Provider | None:
    return db.scalar(select(Provider).where(Provider.license_number == license_number))


def create(db: Session, data: ProviderRegister) -> Provider:
    provider = Provider(
        id=uuid.uuid4(),
        clinic_id=data.clinic_id,
        name=data.name,
        specialty=data.specialty,
        license_number=data.license_number,
        consultation_fee=data.consultation_fee,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
    )
    db.add(provider)
    db.flush()
    return provider


def get_schedule(db: Session, provider_id: uuid.UUID) -> list[ProviderSchedule]:
    return list(
        db.scalars(select(ProviderSchedule).where(ProviderSchedule.provider_id == provider_id))
    )


def replace_schedule(
    db: Session, provider_id: uuid.UUID, entries: list[ProviderScheduleEntry]
) -> list[ProviderSchedule]:
    """Full-replace semantics: PUT /providers/{id}/schedule sends the
    complete weekly template, not a single day's patch."""
    db.execute(delete(ProviderSchedule).where(ProviderSchedule.provider_id == provider_id))
    rows = [
        ProviderSchedule(
            id=uuid.uuid4(),
            provider_id=provider_id,
            day_of_week=entry.day_of_week,
            start_time=entry.start_time,
            end_time=entry.end_time,
            slot_duration_min=entry.slot_duration_min,
        )
        for entry in entries
    ]
    db.add_all(rows)
    db.flush()
    return rows


def add_time_off(db: Session, provider_id: uuid.UUID, data: TimeOffCreate) -> TimeOff:
    """Raises ValueError if this provider already has a time-off entry for
    the exact same date range — otherwise identical resubmissions silently
    pile up with no error at all."""
    duplicate = db.scalar(
        select(TimeOff).where(
            TimeOff.provider_id == provider_id,
            TimeOff.start_date == data.start_date,
            TimeOff.end_date == data.end_date,
        )
    )
    if duplicate is not None:
        raise ValueError("time_off_already_exists")

    time_off = TimeOff(
        id=uuid.uuid4(),
        provider_id=provider_id,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        source=TimeOffSource.MANUAL,
    )
    db.add(time_off)
    db.flush()
    return time_off


def list_time_off(db: Session, provider_id: uuid.UUID) -> list[TimeOff]:
    return list(db.scalars(select(TimeOff).where(TimeOff.provider_id == provider_id)))

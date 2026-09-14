import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from jwt_shared import Role, TokenPayload
from kafka_shared import Topic
from sqlalchemy.orm import Session

from app import crud
from app.db.session import get_db
from app.deps import auth, ensure_self_or_roles
from app.schemas.provider import ProviderRead, ProviderRegister
from app.schemas.schedule import (
    ProviderScheduleRead,
    ProviderScheduleUpdate,
    TimeOffCreate,
    TimeOffRead,
)
from app.services.events import publish
from app.services.slot_reconciliation import trigger_slot_reconciliation

router = APIRouter(prefix="/providers", tags=["providers"])


@router.post(
    "",
    response_model=ProviderRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_roles(Role.ADMIN))],
)
def register_provider(payload: ProviderRegister, db: Session = Depends(get_db)) -> ProviderRead:
    if crud.user.get_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    if crud.provider.get_by_license_number(db, payload.license_number) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "License number already registered")
    provider = crud.provider.create(db, payload)
    crud.user.create(
        db,
        email=payload.email,
        password=payload.password,
        role=Role.PROVIDER,
        provider_id=provider.id,
    )
    db.commit()
    return ProviderRead.model_validate(provider)


@router.get("", response_model=list[ProviderRead])
def list_providers(db: Session = Depends(get_db)) -> list[ProviderRead]:
    return [ProviderRead.model_validate(p) for p in crud.provider.list_all(db)]


@router.get("/{provider_id}", response_model=ProviderRead)
def get_provider(provider_id: uuid.UUID, db: Session = Depends(get_db)) -> ProviderRead:
    provider = crud.provider.get(db, provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    return ProviderRead.model_validate(provider)


@router.get("/{provider_id}/schedule", response_model=list[ProviderScheduleRead])
def get_schedule(
    provider_id: uuid.UUID,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> list[ProviderScheduleRead]:
    ensure_self_or_roles(token, provider_id, Role.ADMIN)
    schedule = crud.provider.get_schedule(db, provider_id)
    return [ProviderScheduleRead.model_validate(s) for s in schedule]


@router.put("/{provider_id}/schedule", response_model=list[ProviderScheduleRead])
def update_schedule(
    provider_id: uuid.UUID,
    payload: ProviderScheduleUpdate,
    background_tasks: BackgroundTasks,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> list[ProviderScheduleRead]:
    ensure_self_or_roles(token, provider_id, Role.ADMIN)
    if crud.provider.get(db, provider_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    rows = crud.provider.replace_schedule(db, provider_id, payload.entries)
    publish(
        db,
        Topic.PROVIDER_SCHEDULE_CHANGED,
        {"provider_id": str(provider_id), "reason": "schedule_updated"},
        actor=str(provider_id),
    )
    db.commit()  # schedule rows + outbox row all commit together
    background_tasks.add_task(trigger_slot_reconciliation, provider_id)
    return [ProviderScheduleRead.model_validate(r) for r in rows]


@router.post(
    "/{provider_id}/time-off", response_model=TimeOffRead, status_code=status.HTTP_201_CREATED
)
def add_time_off(
    provider_id: uuid.UUID,
    payload: TimeOffCreate,
    background_tasks: BackgroundTasks,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> TimeOffRead:
    ensure_self_or_roles(token, provider_id, Role.ADMIN)
    if crud.provider.get(db, provider_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    try:
        time_off = crud.provider.add_time_off(db, provider_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Time-off already exists for this date range"
        ) from exc
    publish(
        db,
        Topic.PROVIDER_SCHEDULE_CHANGED,
        {"provider_id": str(provider_id), "reason": "time_off_added"},
        actor=str(provider_id),
    )
    db.commit()  # time_off row + outbox row all commit together
    background_tasks.add_task(trigger_slot_reconciliation, provider_id)
    return TimeOffRead.model_validate(time_off)


@router.get("/{provider_id}/time-off", response_model=list[TimeOffRead])
def list_time_off(
    provider_id: uuid.UUID,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> list[TimeOffRead]:
    ensure_self_or_roles(token, provider_id, Role.ADMIN)
    return [TimeOffRead.model_validate(t) for t in crud.provider.list_time_off(db, provider_id)]

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response
from jwt_shared import Role, TokenPayload
from sqlalchemy.orm import Session
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from app import crud
from app.core import cache
from app.core.config import get_settings
from app.db.session import get_db
from app.deps import auth, get_temporal_client
from app.schemas.slot import SlotRead
from app.services.slot_generation import (
    compute_candidate_slots,
    fetch_schedule,
    fetch_time_off,
    generate_slots_for_provider,
)
from app.workflows.slot_generation import ReconcileProviderSlotsInput, ReconcileProviderSlotsWorkflow

router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("", response_model=list[SlotRead])
def list_open_slots(
    response: Response,
    provider_id: uuid.UUID | None = None,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> list[SlotRead]:
    """Only ever returns status=open (design §5.1) — a doctor's time off or
    an already-reserved slot never shows up as bookable, by construction.

    Cache-aside, keyed per provider_id (the only filter supported besides
    "all"). The unfiltered case is rare and unbounded in size, so it's
    never cached and never gets an X-Cache header."""
    if provider_id is None:
        return [SlotRead.model_validate(s) for s in crud.slot.list_open(db, provider_id=None)]

    cached = cache.get_slots(provider_id)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    slots = [
        SlotRead.model_validate(s).model_dump(mode="json")
        for s in crud.slot.list_open(db, provider_id=provider_id)
    ]
    cache.set_slots(provider_id, slots)
    response.headers["X-Cache"] = "MISS"
    return slots


@router.post(
    "/generate",
    response_model=list[SlotRead],
    status_code=201,
    dependencies=[Depends(auth.require_roles(Role.ADMIN, Role.FRONT_DESK))],
)
def generate_slots(
    provider_id: uuid.UUID,
    days_ahead: int = 14,
    db: Session = Depends(get_db),
) -> list[SlotRead]:
    """Expands a provider's schedule + time-off (fetched from the profiles
    service) into concrete open Slot rows for the next `days_ahead` days.
    Synchronous and idempotent — safe to call repeatedly; only genuinely
    new slots get inserted (see services/slot_generation.py)."""
    settings = get_settings()
    schedule = fetch_schedule(settings.profiles_base_url, provider_id)
    time_off = fetch_time_off(settings.profiles_base_url, provider_id)
    start_date = datetime.now(timezone.utc).date()
    candidates = compute_candidate_slots(
        schedule, time_off, start_date=start_date, days_ahead=days_ahead
    )
    window_start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    window_end = window_start + timedelta(days=days_ahead)
    new_slots = generate_slots_for_provider(
        db, provider_id, candidates, window_start=window_start, window_end=window_end
    )
    db.commit()
    return [SlotRead.model_validate(s) for s in new_slots]


@router.post("/reconcile", status_code=202)
async def reconcile_slots(
    provider_id: uuid.UUID,
    days_ahead: int = 14,
    client: Client = Depends(get_temporal_client),
) -> dict:
    """Internal, service-to-service trigger — profiles calls this right
    after a provider's schedule or time-off changes, so slots reconcile
    within seconds instead of waiting for the next 24h scheduled run. No
    auth dependency: matches the existing unauthenticated booking->profiles
    schedule/time-off reads (service-to-service trust, not user-facing).
    POST /slots/generate and the 24h Temporal Schedule remain as backups
    if this trigger is missed or booking is unreachable.

    id=f"reconcile-{provider_id}" is deterministic (one provider, one
    identity — no random suffix) specifically so Temporal itself refuses
    a second concurrent reconcile for the same provider while one is
    still running, rather than piling up redundant runs. That's a
    feature, not a bug: whichever run is already in flight reads the
    schedule fresh at execution time, so it still reflects whatever
    triggered this second call. WorkflowAlreadyStartedError is exactly
    that "one's already running" case — not a real error, so it's
    swallowed rather than turning into a 500 for profiles (the caller)."""
    settings = get_settings()
    try:
        await client.start_workflow(
            ReconcileProviderSlotsWorkflow.run,
            ReconcileProviderSlotsInput(provider_id=str(provider_id), days_ahead=days_ahead),
            id=f"reconcile-{provider_id}",
            task_queue=settings.temporal_task_queue,
        )
    except WorkflowAlreadyStartedError:
        pass
    return {"status": "triggered"}

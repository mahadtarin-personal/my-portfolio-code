import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from jwt_shared import Role, TokenPayload
from kafka_shared import Topic
from sqlalchemy.orm import Session
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from tracing_shared import tag_span

from app import crud
from app.core import cache
from app.core.config import get_settings
from app.db.session import get_db
from app.deps import auth, get_temporal_client, limiter
from app.models.appointment import AppointmentStatus
from app.models.calendar_sync_log import CalendarSyncAction
from app.models.reminder_log import ReminderStatus
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
    RescheduleRequest,
)
from app.schemas.visit import VisitRead
from app.services.events import publish
from app.services.waitlist_promotion import PromotionAction, promote_next_waitlisted
from app.tasks.calendar_sync import sync_calendar_task
from app.workflows.booking_saga import BookingSagaInput, BookingSagaWorkflow
from app.workflows.reschedule import RescheduleAppointmentInput, RescheduleAppointmentWorkflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments", tags=["appointments"])

CANCEL_RESCHEDULE_BUFFER = timedelta(minutes=30)


def _ensure_owner_or_staff(token: TokenPayload, patient_id: uuid.UUID) -> None:
    if token.role == Role.PATIENT.value and token.sub != str(patient_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this appointment")


def _ensure_provider_or_staff(token: TokenPayload, provider_id: uuid.UUID) -> None:
    if token.role == Role.PROVIDER.value and token.sub == str(provider_id):
        return
    if token.role in {Role.FRONT_DESK.value, Role.ADMIN.value}:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this resource")


def _ensure_not_too_close_to_start(token: TokenPayload, slot_start_time: datetime) -> None:
    """Patients can't cancel/reschedule within 30 minutes of the slot's
    start — prevents last-second no-shows. Staff (front_desk/admin) bypass
    this for legitimate late changes (e.g. a provider emergency). System-
    triggered waitlist promotion never calls through these HTTP endpoints
    at all, so it's structurally exempt without needing a special case."""
    if token.role != Role.PATIENT.value:
        return
    # SQLite (tests) returns naive datetimes; Postgres returns aware ones.
    # Both are semantically UTC in this app — normalize before comparing,
    # same fix already applied in services/slot_generation.py.
    if slot_start_time.tzinfo is None:
        slot_start_time = slot_start_time.replace(tzinfo=timezone.utc)
    if slot_start_time - datetime.now(timezone.utc) < CANCEL_RESCHEDULE_BUFFER:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Too close to the appointment time to cancel or reschedule",
        )


@router.get("", response_model=list[AppointmentRead])
def list_appointments(
    patient_id: uuid.UUID | None = None,
    provider_id: uuid.UUID | None = None,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> list[AppointmentRead]:
    """Every appointment, any status — pending, confirmed, cancelled,
    completed, failed — filtered by patient (a patient's own bookings; the
    one place to discover an appointment id without already knowing it,
    e.g. after a fresh-booking waitlist promotion) or by provider (a
    provider's schedule of who's booked in, self or front_desk/admin)."""
    if patient_id is not None:
        tag_span(patient_id=str(patient_id))
        _ensure_owner_or_staff(token, patient_id)
        appointments = crud.appointment.list_for_patient(db, patient_id)
    elif provider_id is not None:
        tag_span(provider_id=str(provider_id))
        _ensure_provider_or_staff(token, provider_id)
        appointments = crud.appointment.list_for_provider(db, provider_id)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide patient_id or provider_id")
    return [AppointmentRead.model_validate(a) for a in appointments]


@router.post(
    "",
    response_model=AppointmentRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(auth.require_roles(Role.PATIENT))],
)
@limiter.limit("20/minute")
async def create_appointment(
    request: Request,
    payload: AppointmentCreate,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
    temporal_client: Client = Depends(get_temporal_client),
) -> AppointmentRead:
    """Starts the booking saga asynchronously and returns immediately with a
    PENDING appointment — the client polls GET .../status to watch it move
    pending -> reserved -> payment_pending -> confirmed (or failed), per the
    design doc's real-time status intent (§5). The actual slot reservation,
    billing pre-check, and confirmation happen in BookingSagaWorkflow,
    running in a separate worker process (design §5.2)."""
    tag_span(patient_id=str(payload.patient_id), provider_id=str(payload.provider_id))
    if token.sub != str(payload.patient_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot book on behalf of another patient")

    # Check for a replay BEFORE attempting to create a new row — otherwise a
    # retried request would collide with its own still-active first attempt
    # on the active-slot uniqueness constraint and get a spurious 409
    # instead of the original appointment back.
    #
    # Every db.* call below runs via run_in_threadpool: db is a plain
    # synchronous SQLAlchemy Session (see app/db/session.py), and this
    # handler is async def (it later awaits temporal_client.start_workflow,
    # which is async-native) — calling a blocking Session method directly
    # here would block this process's ONE event loop thread until Postgres
    # responds, stalling every other in-flight request on this process.
    # run_in_threadpool hands the call to a worker thread and awaits it,
    # so the loop stays free while the query is in flight. Calls stay
    # sequential (each awaited before the next starts), so the Session
    # is never touched by two threads at once.
    replay = await run_in_threadpool(
        crud.idempotency.find_active, db, patient_id=payload.patient_id, key=idempotency_key
    )
    if replay is not None:
        tag_span(appointment_id=str(replay.appointment_id))
        existing = await run_in_threadpool(crud.appointment.get, db, replay.appointment_id)
        return AppointmentRead.model_validate(existing)

    appointment_id = uuid.uuid4()
    tag_span(appointment_id=str(appointment_id))
    try:
        appointment = await run_in_threadpool(
            crud.appointment.create_pending,
            db,
            appointment_id=appointment_id,
            patient_id=payload.patient_id,
            provider_id=payload.provider_id,
            slot_id=payload.slot_id,
        )
    except ValueError as exc:
        await run_in_threadpool(db.rollback)
        raise HTTPException(status.HTTP_409_CONFLICT, "Slot is not available") from exc

    # Still handles the genuine race of two concurrent requests with the
    # SAME key both passing the find_active check above before either
    # commits — claim() is an insert guarded by a unique constraint, so
    # exactly one of them wins and the other falls back to that winner's row.
    existing_claim = await run_in_threadpool(
        crud.idempotency.claim,
        db,
        patient_id=payload.patient_id,
        key=idempotency_key,
        appointment_id=appointment_id,
    )
    if existing_claim is not None:
        await run_in_threadpool(db.rollback)  # our own PENDING insert above is
        # discarded — another request already owns this idempotency key
        existing = await run_in_threadpool(crud.appointment.get, db, existing_claim.appointment_id)
        return AppointmentRead.model_validate(existing)

    await run_in_threadpool(db.commit)

    settings = get_settings()
    workflow_id = f"booking-{payload.patient_id}-{idempotency_key}"
    try:
        await temporal_client.start_workflow(
            BookingSagaWorkflow.run,
            BookingSagaInput(
                appointment_id=str(appointment_id),
                patient_id=str(payload.patient_id),
                provider_id=str(payload.provider_id),
                slot_id=str(payload.slot_id),
            ),
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
    except WorkflowAlreadyStartedError:
        # Belt-and-suspenders only — the idempotency table above is the
        # primary guard against a second workflow for the same key.
        pass

    return AppointmentRead.model_validate(appointment)


@router.get("/{appointment_id}/status", response_model=AppointmentRead)
def get_appointment_status(
    appointment_id: uuid.UUID,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
) -> AppointmentRead:
    tag_span(appointment_id=str(appointment_id))
    appointment = crud.appointment.get(db, appointment_id)
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
    tag_span(patient_id=str(appointment.patient_id))
    _ensure_owner_or_staff(token, appointment.patient_id)
    return AppointmentRead.model_validate(appointment)


@router.patch(
    "/{appointment_id}",
    response_model=AppointmentRead,
    dependencies=[Depends(auth.require_roles(Role.PATIENT, Role.FRONT_DESK))],
)
async def update_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
    temporal_client: Client = Depends(get_temporal_client),
) -> AppointmentRead:
    tag_span(appointment_id=str(appointment_id))
    # See create_appointment's comment above for why every db.*/cache.*
    # call below goes through run_in_threadpool: this handler is async def
    # (it later awaits temporal_client.start_workflow), but db is a plain
    # synchronous Session — calling it directly would block this process's
    # one event loop thread for the whole cancellation.
    appointment = await run_in_threadpool(crud.appointment.get, db, appointment_id)
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
    tag_span(patient_id=str(appointment.patient_id), provider_id=str(appointment.provider_id))
    _ensure_owner_or_staff(token, appointment.patient_id)

    if payload.status != AppointmentStatus.CANCELLED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only cancellation is supported for now — reschedule is its own endpoint",
        )

    if appointment.slot is not None:
        _ensure_not_too_close_to_start(token, appointment.slot.start_time)

    provider_id = appointment.provider_id
    freed_slot_id = appointment.slot_id
    try:
        await run_in_threadpool(crud.appointment.cancel, db, appointment)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Appointment cannot be cancelled from its current status"
        ) from exc

    promotion = await run_in_threadpool(promote_next_waitlisted, db, provider_id, freed_slot_id)
    await run_in_threadpool(
        publish,
        db,
        Topic.APPOINTMENT_CANCELLED,
        {
            "appointment_id": str(appointment.id),
            "patient_id": str(appointment.patient_id),
            "provider_id": str(provider_id),
            "slot_id": str(freed_slot_id),
        },
        actor=str(appointment.patient_id),
    )
    # Same transaction as the cancellation itself — a reminder still
    # SCHEDULED for this appointment must not survive it. No-ops cleanly
    # if none exists yet (e.g. cancelled before ever reaching CONFIRMED)
    # or if ReminderWorkflow's send_reminder activity already transitioned
    # it (its own wakeup beat the cancellation) — mark_outcome's WHERE
    # status='scheduled' guard handles both.
    await run_in_threadpool(
        crud.reminder_log.mark_outcome,
        db,
        appointment_id=appointment.id,
        status=ReminderStatus.SKIPPED,
        appointment_status=AppointmentStatus.CANCELLED.value,
    )
    await run_in_threadpool(db.commit)  # cancel + promotion + reminder outcome + outbox row all commit together
    await run_in_threadpool(cache.invalidate_slots, provider_id)

    # Fire-and-forget, outside the transaction — same non-blocking
    # contract as the saga's own use of this task (design §2/§4).
    # sync_calendar_task itself no-ops if no SYNCED event exists yet to
    # revert (e.g. cancelled before ever reaching CONFIRMED).
    #
    # .delay() itself (not just the task body) can raise if the broker is
    # briefly unreachable — caught here, not left to propagate, because
    # this is an HTTP request handler: an uncaught exception here would
    # 500 the cancellation response even though the cancellation itself
    # already committed successfully above. Hit this live (not
    # hypothetical) — a cancellation succeeded but its calendar revert was
    # silently lost because nothing was watching for .delay() to fail.
    try:
        await run_in_threadpool(
            sync_calendar_task.delay,
            str(appointment.id),
            str(provider_id),
            CalendarSyncAction.REVERTED.value,
        )
    except Exception:
        logger.warning(
            "failed to enqueue calendar revert for appointment %s", appointment.id, exc_info=True
        )

    if promotion is not None:
        settings = get_settings()
        if promotion.action == PromotionAction.SHIFT_EXISTING:
            await temporal_client.start_workflow(
                RescheduleAppointmentWorkflow.run,
                RescheduleAppointmentInput(
                    appointment_id=str(promotion.appointment.id),
                    old_slot_id=str(promotion.appointment.slot_id),
                    new_slot_id=str(promotion.slot_id),
                    provider_id=str(promotion.provider_id),
                ),
                id=f"reschedule-{promotion.appointment.id}-to-{promotion.slot_id}",
                task_queue=settings.temporal_task_queue,
            )
        else:
            await temporal_client.start_workflow(
                BookingSagaWorkflow.run,
                BookingSagaInput(
                    appointment_id=str(promotion.appointment.id),
                    patient_id=str(promotion.patient_id),
                    provider_id=str(promotion.provider_id),
                    slot_id=str(promotion.slot_id),
                ),
                id=f"booking-{promotion.appointment.id}",
                task_queue=settings.temporal_task_queue,
            )

    return AppointmentRead.model_validate(appointment)


@router.post(
    "/{appointment_id}/reschedule",
    response_model=AppointmentRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(auth.require_roles(Role.PATIENT, Role.FRONT_DESK))],
)
async def reschedule_appointment(
    appointment_id: uuid.UUID,
    payload: RescheduleRequest,
    token: TokenPayload = Depends(auth),
    db: Session = Depends(get_db),
    temporal_client: Client = Depends(get_temporal_client),
) -> AppointmentRead:
    """Starts RescheduleAppointmentWorkflow asynchronously — same async-start
    pattern as booking. The response still shows the OLD slot_id; poll
    GET .../status to see it move once the workflow's swap step commits."""
    tag_span(appointment_id=str(appointment_id))
    appointment = await run_in_threadpool(crud.appointment.get, db, appointment_id)
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
    tag_span(patient_id=str(appointment.patient_id), provider_id=str(appointment.provider_id))
    _ensure_owner_or_staff(token, appointment.patient_id)

    if appointment.status != AppointmentStatus.CONFIRMED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Only a confirmed appointment can be rescheduled"
        )
    if appointment.slot is not None:
        _ensure_not_too_close_to_start(token, appointment.slot.start_time)

    settings = get_settings()
    await temporal_client.start_workflow(
        RescheduleAppointmentWorkflow.run,
        RescheduleAppointmentInput(
            appointment_id=str(appointment.id),
            old_slot_id=str(appointment.slot_id),
            new_slot_id=str(payload.new_slot_id),
            provider_id=str(appointment.provider_id),
        ),
        id=f"reschedule-{appointment.id}-to-{payload.new_slot_id}",
        task_queue=settings.temporal_task_queue,
    )

    return AppointmentRead.model_validate(appointment)


@router.post(
    "/{appointment_id}/check-in",
    response_model=VisitRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_roles(Role.FRONT_DESK))],
)
def check_in_appointment(appointment_id: uuid.UUID, db: Session = Depends(get_db)) -> VisitRead:
    tag_span(appointment_id=str(appointment_id))
    appointment = crud.appointment.get(db, appointment_id)
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
    tag_span(patient_id=str(appointment.patient_id), provider_id=str(appointment.provider_id))
    try:
        visit = crud.visit.check_in(db, appointment)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return VisitRead.model_validate(visit)


@router.post(
    "/{appointment_id}/start",
    response_model=VisitRead,
    dependencies=[Depends(auth.require_roles(Role.PROVIDER))],
)
def start_visit(appointment_id: uuid.UUID, db: Session = Depends(get_db)) -> VisitRead:
    tag_span(appointment_id=str(appointment_id))
    appointment = crud.appointment.get(db, appointment_id)
    if appointment is None or appointment.visit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visit not found")
    tag_span(patient_id=str(appointment.patient_id), provider_id=str(appointment.provider_id))
    try:
        visit = crud.visit.start(db, appointment.visit)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return VisitRead.model_validate(visit)


@router.post(
    "/{appointment_id}/complete",
    response_model=VisitRead,
    dependencies=[Depends(auth.require_roles(Role.PROVIDER))],
)
def complete_visit(appointment_id: uuid.UUID, db: Session = Depends(get_db)) -> VisitRead:
    tag_span(appointment_id=str(appointment_id))
    appointment = crud.appointment.get(db, appointment_id)
    if appointment is None or appointment.visit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visit not found")
    tag_span(patient_id=str(appointment.patient_id), provider_id=str(appointment.provider_id))
    try:
        visit = crud.visit.complete(db, appointment.visit)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    publish(
        db,
        Topic.VISIT_COMPLETED,
        {
            "appointment_id": str(appointment.id),
            "patient_id": str(appointment.patient_id),
            "provider_id": str(appointment.provider_id),
            "checked_in_at": visit.checked_in_at.isoformat(),
            "started_at": visit.started_at.isoformat(),
            "completed_at": visit.completed_at.isoformat(),
        },
        actor=str(appointment.patient_id),
    )
    db.commit()  # visit completion + outbox row commit together
    return VisitRead.model_validate(visit)

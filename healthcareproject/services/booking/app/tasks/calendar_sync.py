from __future__ import annotations

import logging
import uuid

from app.celery_app import celery_app
from app.core.config import get_settings
from app.crud import calendar_sync_log as calendar_sync_crud
from app.db.session import session_scope
from app.models.appointment import Appointment
from app.models.calendar_sync_log import CalendarSyncAction
from app.services import google_calendar

logger = logging.getLogger(__name__)
 
_VERBS = {
    CalendarSyncAction.SYNCED: "pushed confirmed booking",
    CalendarSyncAction.REVERTED: "removed reverted booking",
    CalendarSyncAction.RESCHEDULED: "moved rescheduled booking",
}
# SYNCED/REVERTED each happen at most once per appointment, ever — worth
# checking before touching the real API. RESCHEDULED doesn't: the same
# appointment can legitimately be rescheduled more than once, each one
# its own row (see CalendarSyncLog's docstring for why that's safe).
_ONCE_PER_APPOINTMENT = {CalendarSyncAction.SYNCED, CalendarSyncAction.REVERTED}


@celery_app.task(name="booking.sync_calendar_task", bind=True, max_retries=3, default_retry_delay=5)
def sync_calendar_task(self, appointment_id: str, provider_id: str, action: str) -> None:
    """Stubbed by default — see CalendarSyncLog's docstring. When
    settings.google_calendar_enabled is on (real OAuth credentials
    configured, app/services/google_calendar.py), this actually creates,
    deletes, or moves an event on a real calendar. Runs fire-and-forget
    off the saga/reschedule workflow (design §2/§4 — "Booking -> Celery:
    async, not blocking the booking"): the caller never waits on it, so a
    slow or failed calendar push can never block or fail a booking or
    reschedule. Recorded in this service's own DB, not published to
    Kafka — this is an internal side effect, not a domain event other
    services need to react to."""
    sync_action = CalendarSyncAction(action)
    settings = get_settings()
    appointment_uuid = uuid.UUID(appointment_id)

    with session_scope() as db:
        # Checked BEFORE calling the real API (not just at insert time) —
        # a retry that got past this on a first attempt would otherwise
        # create a second real calendar event and then discard its id
        # when record() finds the row already exists, leaving an orphan
        # on the actual calendar. Skipped for RESCHEDULED, which is
        # allowed to happen more than once.
        if sync_action in _ONCE_PER_APPOINTMENT:
            if calendar_sync_crud.get(db, appointment_id=appointment_uuid, action=sync_action) is not None:
                logger.info(
                    "calendar sync %s already recorded for appointment %s, skipping", action, appointment_id
                )
                return

        external_event_id = None
        if settings.google_calendar_enabled:
            if sync_action is CalendarSyncAction.SYNCED:
                appointment = db.get(Appointment, appointment_uuid)
                if appointment is not None:
                    external_event_id = google_calendar.create_event(
                        summary=f"SmartHealth appointment {appointment_id}",
                        description=f"Patient {appointment.patient_id} / Provider {appointment.provider_id}",
                        start=appointment.slot.start_time,
                        end=appointment.slot.end_time,
                    )
            elif sync_action is CalendarSyncAction.REVERTED:
                prior = calendar_sync_crud.get(
                    db, appointment_id=appointment_uuid, action=CalendarSyncAction.SYNCED
                )
                if prior is not None and prior.external_event_id:
                    google_calendar.delete_event(prior.external_event_id)
            else:  # RESCHEDULED — move the SAME real event, don't create a new one
                appointment = db.get(Appointment, appointment_uuid)
                prior = calendar_sync_crud.get(
                    db, appointment_id=appointment_uuid, action=CalendarSyncAction.SYNCED
                )
                if appointment is not None and prior is not None and prior.external_event_id:
                    google_calendar.update_event(
                        prior.external_event_id,
                        start=appointment.slot.start_time,
                        end=appointment.slot.end_time,
                    )
                    external_event_id = prior.external_event_id

        row = calendar_sync_crud.record(
            db,
            appointment_id=appointment_uuid,
            provider_id=uuid.UUID(provider_id),
            action=sync_action,
            external_event_id=external_event_id,
        )
        if row is None:
            # Lost a race against another attempt of this same task
            # between the check above and this insert — rare, and for a
            # real event means an orphan could be left on the calendar
            # (acceptable for this stage; a production version would wrap
            # the check+insert in a DB-level lock). Not reachable for
            # RESCHEDULED, which has no such uniqueness to race against.
            logger.info(
                "calendar sync %s already recorded for appointment %s, skipping", action, appointment_id
            )
            return
    logger.info(
        "calendar: %s %s (provider %s)%s",
        _VERBS[sync_action],
        appointment_id,
        provider_id,
        f" [event {external_event_id}]" if external_event_id else "",
    )

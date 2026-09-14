from __future__ import annotations

from datetime import datetime

import httpx

from app.core.config import get_settings

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"


def _access_token() -> str:
    """Exchanges the long-lived refresh token (minted once via a local
    OAuth consent flow, see scripts/google_calendar_oauth.py) for a
    short-lived access token — done on every call rather than cached,
    since this only ever fires from a fire-and-forget Celery task, not a
    hot path (design §2/§4)."""
    settings = get_settings()
    response = httpx.post(
        _TOKEN_URL,
        data={
            "client_id": settings.google_calendar_client_id,
            "client_secret": settings.google_calendar_client_secret,
            "refresh_token": settings.google_calendar_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def create_event(*, summary: str, description: str, start: datetime, end: datetime) -> str:
    """Returns the created event's Google-assigned id — sync_calendar_task
    stores this on the CalendarSyncLog row so a later REVERTED action
    knows exactly which event to delete."""
    settings = get_settings()
    response = httpx.post(
        _EVENTS_URL.format(calendar_id=settings.google_calendar_id),
        headers={"Authorization": f"Bearer {_access_token()}"},
        json={
            "summary": summary,
            "description": description,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["id"]


def update_event(event_id: str, *, start: datetime, end: datetime) -> None:
    """PATCH, not PUT — only touches start/end, leaves summary/description
    untouched (they still correctly describe the same appointment_id,
    which doesn't change on a reschedule, only its slot does)."""
    settings = get_settings()
    response = httpx.patch(
        f"{_EVENTS_URL.format(calendar_id=settings.google_calendar_id)}/{event_id}",
        headers={"Authorization": f"Bearer {_access_token()}"},
        json={
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        },
        timeout=10.0,
    )
    response.raise_for_status()


def delete_event(event_id: str) -> None:
    """404/410 are treated as success — the event is already gone (e.g. a
    human deleted it manually), which is exactly the end state a revert
    wants, not a failure to raise/retry over."""
    settings = get_settings()
    response = httpx.delete(
        f"{_EVENTS_URL.format(calendar_id=settings.google_calendar_id)}/{event_id}",
        headers={"Authorization": f"Bearer {_access_token()}"},
        timeout=10.0,
    )
    if response.status_code not in (204, 404, 410):
        response.raise_for_status()

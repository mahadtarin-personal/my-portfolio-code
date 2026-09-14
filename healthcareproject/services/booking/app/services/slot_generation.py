from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import get_settings
from app.models.slot import Slot, SlotStatus


def _service_auth_header() -> dict[str, str]:
    """profiles' GET /providers/{id}/schedule and /time-off require auth —
    booking has no user token to forward here (this call isn't triggered by
    an end-user request). Under RS256, booking has no private key at all,
    so it can't self-mint a credential the way it used to (that used the
    shared JWT_SECRET both services held under HS256 — the exact thing
    RS256 was adopted to stop being possible: any service holding a
    shared secret could forge an admin token for itself). Instead it asks
    profiles for a real one, authenticated by a separate, narrow-purpose
    shared secret that can never itself sign a token."""
    settings = get_settings()
    response = httpx.post(
        f"{settings.profiles_base_url}/auth/service-token",
        json={"service_name": "booking"},
        headers={"X-Service-Secret": settings.service_auth_secret},
        timeout=10.0,
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def fetch_schedule(profiles_base_url: str, provider_id: uuid.UUID) -> list[dict]:
    response = httpx.get(
        f"{profiles_base_url}/providers/{provider_id}/schedule",
        headers=_service_auth_header(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_time_off(profiles_base_url: str, provider_id: uuid.UUID) -> list[dict]:
    response = httpx.get(
        f"{profiles_base_url}/providers/{provider_id}/time-off",
        headers=_service_auth_header(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def _is_on_time_off(day: date, time_off_entries: list[dict]) -> bool:
    for entry in time_off_entries:
        start = date.fromisoformat(entry["start_date"])
        end = date.fromisoformat(entry["end_date"])
        if start <= day <= end:
            return True
    return False


def compute_candidate_slots(
    schedule_entries: list[dict],
    time_off_entries: list[dict],
    start_date: date,
    days_ahead: int,
    *,
    now: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """Pure function, no DB/HTTP — expands a provider's weekly schedule +
    time-off exceptions into concrete (start, end) datetime windows.

    day_of_week is an int enum (Monday=0..Sunday=6, see
    profiles/app/models/schedule.py::DayOfWeek) matching date.weekday()
    exactly, so no translation is needed. Times are treated as UTC, the
    same convention Slot.start_time/end_time already use everywhere else.
    """
    now = now or datetime.now(timezone.utc)
    candidates: list[tuple[datetime, datetime]] = []

    for offset in range(days_ahead):
        day = start_date + timedelta(days=offset)
        if _is_on_time_off(day, time_off_entries):
            continue

        for entry in schedule_entries:
            if entry["day_of_week"] != day.weekday():
                continue

            duration = timedelta(minutes=entry["slot_duration_min"])
            cursor = datetime.combine(day, time.fromisoformat(entry["start_time"]), tzinfo=timezone.utc)
            day_end = datetime.combine(day, time.fromisoformat(entry["end_time"]), tzinfo=timezone.utc)

            while cursor + duration <= day_end:
                if cursor >= now:
                    candidates.append((cursor, cursor + duration))
                cursor += duration

    return candidates


def _as_utc(value: datetime) -> datetime:
    """SQLite (used in tests) returns naive datetimes; Postgres returns
    timezone-aware ones. Both are semantically UTC in this app, so
    normalize before comparing — otherwise duplicate-detection would
    silently fail to match on SQLite."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def generate_slots_for_provider(
    db: Session,
    provider_id: uuid.UUID,
    candidates: list[tuple[datetime, datetime]],
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[Slot]:
    """Reconciles OPEN/BLOCKED slots for this provider within
    [window_start, window_end) against the current candidate set (the
    provider's live schedule + time-off, expanded by compute_candidate_slots):

    - A candidate with no existing slot -> create OPEN (plain generation).
    - A candidate matching an existing BLOCKED slot -> reopen it (schedule
      or time-off changed back in its favor).
    - An existing OPEN slot whose start is no longer a candidate -> BLOCKED.

    RESERVED slots are never touched here regardless of candidate
    membership — an appointment already exists on them, and a provider
    retroactively blocking a booked slot is a real conflict (needs
    cancellation + notification) that's out of scope for reconciliation.

    Returns only the newly created slots (unchanged contract for existing
    callers) — reopened/blocked slots are side effects, not the return
    value."""
    candidate_starts = {start for start, _ in candidates}
    existing = list(
        db.scalars(
            select(Slot).where(
                Slot.provider_id == provider_id,
                Slot.start_time >= window_start,
                Slot.start_time < window_end,
                Slot.status.in_([SlotStatus.OPEN, SlotStatus.BLOCKED]),
            )
        )
    )
    existing_by_start = {_as_utc(s.start_time): s for s in existing}

    new_slots = [
        Slot(id=uuid.uuid4(), provider_id=provider_id, start_time=start, end_time=end, status=SlotStatus.OPEN)
        for start, end in candidates
        if start not in existing_by_start
    ]
    db.add_all(new_slots)

    changed = bool(new_slots)
    for start, slot in existing_by_start.items():
        if start in candidate_starts and slot.status == SlotStatus.BLOCKED:
            slot.status = SlotStatus.OPEN
            changed = True
        elif start not in candidate_starts and slot.status == SlotStatus.OPEN:
            slot.status = SlotStatus.BLOCKED
            changed = True

    db.flush()

    if changed:
        cache.invalidate_slots(provider_id)

    return new_slots

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from temporalio import activity

from app.core.config import get_settings
from app.db.session import session_scope
from app.services.slot_generation import (
    compute_candidate_slots,
    fetch_schedule,
    fetch_time_off,
    generate_slots_for_provider,
)


@dataclass
class GenerateForProviderInput:
    provider_id: str
    days_ahead: int


@activity.defn
def list_provider_ids() -> list[str]:
    settings = get_settings()
    response = httpx.get(f"{settings.profiles_base_url}/providers", timeout=10.0)
    response.raise_for_status()
    return [provider["id"] for provider in response.json()]


@activity.defn
def generate_slots_for_one_provider(inp: GenerateForProviderInput) -> int:
    settings = get_settings()
    provider_id = uuid.UUID(inp.provider_id)
    schedule = fetch_schedule(settings.profiles_base_url, provider_id)
    time_off = fetch_time_off(settings.profiles_base_url, provider_id)
    start_date = datetime.now(timezone.utc).date()
    candidates = compute_candidate_slots(
        schedule, time_off, start_date=start_date, days_ahead=inp.days_ahead
    )
    window_start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    window_end = window_start + timedelta(days=inp.days_ahead)
    with session_scope() as db:
        new_slots = generate_slots_for_provider(
            db, provider_id, candidates, window_start=window_start, window_end=window_end
        )
        return len(new_slots)

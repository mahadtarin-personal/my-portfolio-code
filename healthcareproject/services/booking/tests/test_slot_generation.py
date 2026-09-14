import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jwt_shared import Role
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app import crud
from app.activities.slot_generation import GenerateForProviderInput
from app.core.config import get_settings
from app.models.slot import Slot, SlotStatus
from app.services.slot_generation import compute_candidate_slots, fetch_schedule, generate_slots_for_provider
from app.workflows.slot_generation import (
    GenerateSlotsScheduledWorkflow,
    ReconcileProviderSlotsInput,
    ReconcileProviderSlotsWorkflow,
)
from tests.conftest import auth_header

TASK_QUEUE = "test-slot-generation"


class _FakeResponse:
    def __init__(self, json_body: dict | list) -> None:
        self._json_body = json_body

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict | list:
        return self._json_body


# ---- _service_auth_header / fetch_schedule: the RS256 service-token flow ----


def test_fetch_schedule_asks_profiles_for_a_service_token_first(monkeypatch) -> None:
    """Booking can't self-mint a credential under RS256 (no private key) —
    it has to call profiles' POST /auth/service-token, authenticated by
    the shared service_auth_secret, then use THAT real token on the
    actual GET /providers/{id}/schedule call."""
    settings = get_settings()
    calls = []

    def _fake_post(url, *, json=None, headers=None, timeout=None):
        calls.append(("POST", url, json, headers))
        return _FakeResponse({"access_token": "real-token-from-profiles"})

    def _fake_get(url, *, headers=None, timeout=None):
        calls.append(("GET", url, headers))
        return _FakeResponse([])

    monkeypatch.setattr("app.services.slot_generation.httpx.post", _fake_post)
    monkeypatch.setattr("app.services.slot_generation.httpx.get", _fake_get)

    provider_id = uuid.uuid4()
    fetch_schedule(settings.profiles_base_url, provider_id)

    assert len(calls) == 2
    method, url, json_body, post_headers = calls[0]
    assert method == "POST"
    assert url == f"{settings.profiles_base_url}/auth/service-token"
    assert json_body == {"service_name": "booking"}
    assert post_headers == {"X-Service-Secret": settings.service_auth_secret}

    method, url, get_headers = calls[1]
    assert method == "GET"
    assert url == f"{settings.profiles_base_url}/providers/{provider_id}/schedule"
    assert get_headers == {"Authorization": "Bearer real-token-from-profiles"}


def _next_weekday(base: date, weekday: int) -> date:
    return base + timedelta(days=(weekday - base.weekday()) % 7)


# ---- compute_candidate_slots: pure function, no DB/HTTP needed ----


def test_compute_candidate_slots_basic():
    monday = _next_weekday(date(2026, 1, 1), 0)
    schedule = [{"day_of_week": 0, "start_time": "09:00:00", "end_time": "10:00:00", "slot_duration_min": 30}]
    candidates = compute_candidate_slots(
        schedule, [], start_date=monday, days_ahead=7, now=datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    assert candidates == [
        (
            datetime.combine(monday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=9),
            datetime.combine(monday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=9, minutes=30),
        ),
        (
            datetime.combine(monday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=9, minutes=30),
            datetime.combine(monday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10),
        ),
    ]


def test_compute_candidate_slots_excludes_time_off_dates():
    monday = _next_weekday(date(2026, 1, 1), 0)
    schedule = [{"day_of_week": 0, "start_time": "09:00:00", "end_time": "09:30:00", "slot_duration_min": 30}]
    time_off = [{"start_date": monday.isoformat(), "end_date": monday.isoformat()}]

    candidates = compute_candidate_slots(
        schedule, time_off, start_date=monday, days_ahead=14, now=datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    # the first Monday is on time-off, so only the second Monday (7 days later) should produce a slot
    assert len(candidates) == 1
    assert candidates[0][0].date() == monday + timedelta(days=7)


def test_compute_candidate_slots_no_matching_weekday_produces_nothing():
    monday = _next_weekday(date(2026, 1, 1), 0)
    schedule = [{"day_of_week": 5, "start_time": "09:00:00", "end_time": "10:00:00", "slot_duration_min": 30}]
    candidates = compute_candidate_slots(
        schedule, [], start_date=monday, days_ahead=1, now=datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    assert candidates == []


def test_compute_candidate_slots_excludes_past_slots():
    monday = _next_weekday(date(2026, 1, 1), 0)
    schedule = [{"day_of_week": 0, "start_time": "09:00:00", "end_time": "10:00:00", "slot_duration_min": 30}]
    # "now" is exactly at the second slot's start — the first slot (09:00-09:30) is already in the past
    now = datetime.combine(monday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=9, minutes=30)
    candidates = compute_candidate_slots(schedule, [], start_date=monday, days_ahead=1, now=now)
    assert len(candidates) == 1
    assert candidates[0][0] == now


# ---- POST /slots/generate: endpoint-level, HTTP fetch mocked ----


def test_generate_slots_endpoint_creates_and_is_idempotent(client: TestClient, monkeypatch) -> None:
    provider_id = uuid.uuid4()
    schedule = [
        {"day_of_week": d, "start_time": "09:00:00", "end_time": "09:30:00", "slot_duration_min": 30}
        for d in range(7)
    ]
    monkeypatch.setattr("app.routers.slots.fetch_schedule", lambda base_url, pid: schedule)
    monkeypatch.setattr("app.routers.slots.fetch_time_off", lambda base_url, pid: [])

    headers = auth_header("admin-1", Role.ADMIN)
    first = client.post(f"/slots/generate?provider_id={provider_id}&days_ahead=14", headers=headers)
    assert first.status_code == 201
    assert len(first.json()) >= 1

    second = client.post(f"/slots/generate?provider_id={provider_id}&days_ahead=14", headers=headers)
    assert second.status_code == 201
    assert second.json() == []  # re-running creates nothing new


def test_generate_slots_requires_admin_or_front_desk(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.routers.slots.fetch_schedule", lambda base_url, pid: [])
    monkeypatch.setattr("app.routers.slots.fetch_time_off", lambda base_url, pid: [])
    headers = auth_header("patient-1", Role.PATIENT)
    response = client.post(f"/slots/generate?provider_id={uuid.uuid4()}", headers=headers)
    assert response.status_code == 403


# ---- generate_slots_for_provider: reconciliation (block/reopen), not just additive ----


def _window(start: datetime) -> tuple[datetime, datetime]:
    return start - timedelta(hours=1), start + timedelta(days=2)


def test_reconciliation_blocks_open_slot_no_longer_a_candidate(db) -> None:
    provider_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = crud.slot.create(db, provider_id=provider_id, start_time=start, end_time=start + timedelta(minutes=20))
    db.commit()

    window_start, window_end = _window(start)
    new_slots = generate_slots_for_provider(
        db, provider_id, candidates=[], window_start=window_start, window_end=window_end
    )
    db.commit()

    assert new_slots == []
    assert db.get(Slot, slot.id).status == SlotStatus.BLOCKED


def test_reconciliation_reopens_blocked_slot_back_in_candidates(db) -> None:
    provider_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(minutes=20)
    slot = crud.slot.create(db, provider_id=provider_id, start_time=start, end_time=end)
    slot.status = SlotStatus.BLOCKED
    db.commit()

    window_start, window_end = _window(start)
    new_slots = generate_slots_for_provider(
        db, provider_id, candidates=[(start, end)], window_start=window_start, window_end=window_end
    )
    db.commit()

    assert new_slots == []  # reopened, not newly created
    assert db.get(Slot, slot.id).status == SlotStatus.OPEN


def test_reconciliation_never_touches_reserved_slot(db) -> None:
    provider_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = crud.slot.create(db, provider_id=provider_id, start_time=start, end_time=start + timedelta(minutes=20))
    slot.status = SlotStatus.RESERVED
    db.commit()

    window_start, window_end = _window(start)
    generate_slots_for_provider(
        db, provider_id, candidates=[], window_start=window_start, window_end=window_end
    )
    db.commit()

    # No candidates at all means this slot's start isn't one — reconciliation
    # must still leave a RESERVED (already-booked) slot alone.
    assert db.get(Slot, slot.id).status == SlotStatus.RESERVED


def test_generate_slots_endpoint_blocks_slots_dropped_from_schedule(
    client: TestClient, monkeypatch
) -> None:
    provider_id = uuid.uuid4()
    schedule_full = [
        {"day_of_week": d, "start_time": "09:00:00", "end_time": "09:30:00", "slot_duration_min": 30}
        for d in range(7)
    ]
    monkeypatch.setattr("app.routers.slots.fetch_schedule", lambda base_url, pid: schedule_full)
    monkeypatch.setattr("app.routers.slots.fetch_time_off", lambda base_url, pid: [])

    admin_headers = auth_header("admin-1", Role.ADMIN)
    created = client.post(
        f"/slots/generate?provider_id={provider_id}&days_ahead=14", headers=admin_headers
    ).json()
    assert len(created) >= 1
    expected_monday_count = sum(
        1 for s in created if datetime.fromisoformat(s["start_time"]).weekday() == 0
    )

    # Provider's schedule now only covers Monday — every other day's
    # already-generated open slot should become blocked, not stay open.
    monkeypatch.setattr("app.routers.slots.fetch_schedule", lambda base_url, pid: [schedule_full[0]])
    second = client.post(
        f"/slots/generate?provider_id={provider_id}&days_ahead=14", headers=admin_headers
    )
    assert second.status_code == 201
    assert second.json() == []  # nothing NEW created, only reconciled

    patient_headers = auth_header("patient-1", Role.PATIENT)
    remaining = client.get(f"/slots?provider_id={provider_id}", headers=patient_headers).json()
    assert len(remaining) == expected_monday_count
    assert all(datetime.fromisoformat(s["start_time"]).weekday() == 0 for s in remaining)


# ---- ReconcileProviderSlotsWorkflow: event-triggered, single provider ----


async def test_reconcile_provider_slots_workflow_calls_activity_once_for_that_provider() -> None:
    calls = []

    @activity.defn(name="generate_slots_for_one_provider")
    def fake_generate(inp: GenerateForProviderInput) -> int:
        calls.append(inp.provider_id)
        return 2

    target_provider_id = str(uuid.uuid4())

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[ReconcileProviderSlotsWorkflow],
            activities=[fake_generate],
            activity_executor=ThreadPoolExecutor(max_workers=10),
        ):
            result = await env.client.execute_workflow(
                ReconcileProviderSlotsWorkflow.run,
                ReconcileProviderSlotsInput(provider_id=target_provider_id, days_ahead=14),
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert result == 2
    assert calls == [target_provider_id]


# ---- GenerateSlotsScheduledWorkflow: real Temporal test environment ----


async def test_generate_slots_scheduled_workflow_calls_per_provider_activity() -> None:
    calls = []

    @activity.defn(name="list_provider_ids")
    def fake_list_provider_ids() -> list[str]:
        return [str(uuid.uuid4()), str(uuid.uuid4())]

    @activity.defn(name="generate_slots_for_one_provider")
    def fake_generate(inp: GenerateForProviderInput) -> int:
        calls.append(inp.provider_id)
        return 3

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[GenerateSlotsScheduledWorkflow],
            activities=[fake_list_provider_ids, fake_generate],
            activity_executor=ThreadPoolExecutor(max_workers=10),
        ):
            result = await env.client.execute_workflow(
                GenerateSlotsScheduledWorkflow.run,
                14,
                id=f"test-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert result.providers_processed == 2
    assert result.slots_created == 6
    assert len(calls) == 2

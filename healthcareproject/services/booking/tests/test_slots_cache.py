import uuid

import fakeredis
import pytest
import redis
from jwt_shared import Role

from app import crud
from app.core import cache
from app.models.slot import Slot
from tests.conftest import auth_header


@pytest.fixture
def fake_redis(monkeypatch):
    """Swaps the real Redis client for a fakeredis instance, shared across
    every call within one test — same reasoning as the fake_temporal_client
    fixture: we want a real cache-shaped object, not a mock of one."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "get_client", lambda: fake)
    return fake


class _BrokenRedis:
    """Every call raises, simulating Redis being unreachable — proves the
    cache fails open instead of taking GET /slots down with it."""

    def get(self, key):
        raise redis.RedisError("boom")

    def set(self, key, value, ex=None):
        raise redis.RedisError("boom")

    def delete(self, key):
        raise redis.RedisError("boom")


def test_slots_cache_miss_then_hit(client, open_slot: Slot, fake_redis, monkeypatch) -> None:
    headers = auth_header(uuid.uuid4(), Role.PATIENT)
    calls = {"count": 0}
    original_list_open = crud.slot.list_open

    def counting_list_open(db, *, provider_id=None):
        calls["count"] += 1
        return original_list_open(db, provider_id=provider_id)

    monkeypatch.setattr(crud.slot, "list_open", counting_list_open)

    first = client.get(f"/slots?provider_id={open_slot.provider_id}", headers=headers)
    assert first.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    assert calls["count"] == 1

    second = client.get(f"/slots?provider_id={open_slot.provider_id}", headers=headers)
    assert second.status_code == 200
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()
    assert calls["count"] == 1  # the DB was not hit again


def test_slots_cache_invalidated_after_direct_invalidate_call(
    client, open_slot: Slot, fake_redis
) -> None:
    headers = auth_header(uuid.uuid4(), Role.PATIENT)

    first = client.get(f"/slots?provider_id={open_slot.provider_id}", headers=headers)
    assert first.headers["X-Cache"] == "MISS"

    hit = client.get(f"/slots?provider_id={open_slot.provider_id}", headers=headers)
    assert hit.headers["X-Cache"] == "HIT"

    cache.invalidate_slots(open_slot.provider_id)

    third = client.get(f"/slots?provider_id={open_slot.provider_id}", headers=headers)
    assert third.headers["X-Cache"] == "MISS"


def test_slots_cache_fails_open_when_redis_errors(
    client, open_slot: Slot, monkeypatch
) -> None:
    monkeypatch.setattr(cache, "get_client", lambda: _BrokenRedis())
    headers = auth_header(uuid.uuid4(), Role.PATIENT)

    response = client.get(f"/slots?provider_id={open_slot.provider_id}", headers=headers)
    assert response.status_code == 200
    assert any(s["id"] == str(open_slot.id) for s in response.json())
    assert response.headers.get("X-Cache") != "HIT"


def test_unfiltered_slots_list_has_no_cache_header(client, open_slot: Slot, fake_redis) -> None:
    headers = auth_header(uuid.uuid4(), Role.PATIENT)
    response = client.get("/slots", headers=headers)
    assert response.status_code == 200
    assert "X-Cache" not in response.headers

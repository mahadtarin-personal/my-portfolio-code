from __future__ import annotations

import json
import logging
import random
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable, TypeVar

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None

# Bounds the *wall-clock* time a caller waits on any single cache
# operation, no matter what's slow underneath. redis-py's own
# socket_connect_timeout/socket_timeout only cover the TCP layer — they
# do nothing for a hung DNS lookup (getaddrinfo has no timeout of its
# own), and a stopped Redis container's hostname failing to resolve has
# been observed to block for ~10s. Running each call in a worker thread
# and bounding it with future.result(timeout=...) is what actually
# guarantees fail-open stays fast.
CACHE_CALL_TIMEOUT_SECONDS = 1.5
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="slots-cache")

T = TypeVar("T")


def _with_deadline(fn: Callable[[], T]) -> T | None:
    future: Future = _executor.submit(fn)
    try:
        return future.result(timeout=CACHE_CALL_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        logger.warning(
            "slots cache call exceeded %.1fs deadline, falling back", CACHE_CALL_TIMEOUT_SECONDS
        )
        return None
    except redis.RedisError:
        logger.warning("slots cache call failed", exc_info=True)
        return None


def get_client() -> redis.Redis | None:
    """Lazily builds and memoizes a singleton. Kept as a plain function
    (not @lru_cache) so tests can monkeypatch it directly to return a
    shared fakeredis instance."""
    global _client
    settings = get_settings()
    if not settings.redis_enabled:
        return None
    if _client is None:
        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


def _key(provider_id: uuid.UUID) -> str:
    return f"slots:provider:{provider_id}"


def get_slots(provider_id: uuid.UUID) -> list[dict] | None:
    """None covers disabled/miss/error/timeout alike — the caller's only
    decision on None is "go to the DB", regardless of which it was."""
    client = get_client()
    if client is None:
        return None
    raw = _with_deadline(lambda: client.get(_key(provider_id)))
    return json.loads(raw) if raw is not None else None


def set_slots(provider_id: uuid.UUID, slots: list[dict]) -> None:
    client = get_client()
    if client is None:
        return
    settings = get_settings()
    ttl = settings.slots_cache_ttl_seconds + random.randint(0, settings.slots_cache_ttl_jitter_seconds)
    _with_deadline(lambda: client.set(_key(provider_id), json.dumps(slots), ex=ttl))


def invalidate_slots(provider_id: uuid.UUID) -> None:
    client = get_client()
    if client is None:
        return
    _with_deadline(lambda: client.delete(_key(provider_id)))

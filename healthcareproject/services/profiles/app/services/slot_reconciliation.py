from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# httpx's own timeout=... only bounds the TCP/read layer — it does nothing
# for a hung DNS lookup (getaddrinfo has no timeout of its own), which is
# exactly what happens when `booking` is unreachable/stopped. Learned this
# the hard way building the Redis cache's fail-open path (app/core/cache.py
# in booking): a dead hostname can block for ~10s despite a socket-level
# timeout. Running the call in a worker thread with a hard wall-clock
# deadline is what actually guarantees this stays fast.
TRIGGER_TIMEOUT_SECONDS = 2.0
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="slot-reconcile-trigger")


def _post_reconcile(provider_id: uuid.UUID) -> None:
    settings = get_settings()
    httpx.post(
        f"{settings.booking_base_url}/slots/reconcile",
        params={"provider_id": str(provider_id)},
        timeout=2.0,
    )


def trigger_slot_reconciliation(provider_id: uuid.UUID) -> None:
    """Best-effort — booking being slow/unreachable must never break a
    schedule or time-off write. The 24h Temporal Schedule and the manual
    POST /slots/generate endpoint in booking remain as backups if this
    call fails, times out, or is never made."""
    future = _executor.submit(_post_reconcile, provider_id)
    try:
        future.result(timeout=TRIGGER_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        logger.warning(
            "slot reconciliation trigger for provider %s exceeded %.1fs deadline",
            provider_id,
            TRIGGER_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError:
        logger.warning("slot reconciliation trigger failed for provider %s", provider_id, exc_info=True)

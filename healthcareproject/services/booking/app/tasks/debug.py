from __future__ import annotations

import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="booking.debug_task")
def debug_task(message: str = "ping") -> str:
    """Round-trip smoke test for the broker/worker wiring itself, not part
    of any saga step — the calendar-sync and reminder tasks that are the
    actual point of adding Celery register on this same app afterward."""
    logger.info("debug_task received: %s", message)
    return f"pong: {message}"

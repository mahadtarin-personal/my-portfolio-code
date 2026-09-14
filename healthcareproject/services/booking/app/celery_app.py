from __future__ import annotations

import sys

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging
from logging_shared import configure_logging

from app.core.config import get_settings


@setup_logging.connect
def _configure_celery_logging(**kwargs: object) -> None:
    """Connecting to this signal tells Celery to skip its own default
    logging setup entirely and defer to this instead — same JSON shape
    every other service uses. celery-worker and celery-beat run this same
    module, distinguished only by their CLI subcommand (argv), which is
    the only way from in here to tell which one a given process is."""
    configure_logging("celery-beat" if "beat" in sys.argv else "celery-worker")

settings = get_settings()

# Reuses the same Redis instance booking already has for the slots cache
# (app/core/cache.py) as both broker and result backend — no new
# infrastructure, same reasoning as app/worker.py's docstring for why
# slot generation stayed on a Temporal Schedule instead of Celery. This is
# for genuinely fire-and-forget, non-saga work instead: calendar sync and
# reminders (design doc §2/§4 — "Booking -> Celery: async, fire-and-forget"),
# plus the nightly audit hash-chain check (§13), none of which belong in a
# Temporal saga since none of them need retries-with-compensation semantics.
celery_app = Celery(
    "booking",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Pakistan Standard Time (UTC+5, no DST) — this project runs for a
    # Pakistan-based team, so "2am" in the schedule below and in Celery's
    # own log timestamps should mean 2am PKT, not 2am UTC. enable_utc
    # stays True: Celery still stores/compares task timestamps in UTC
    # internally (correct regardless of locale) — `timezone` only affects
    # how crontab() schedules and logged times are interpreted/displayed.
    timezone="Asia/Karachi",
    enable_utc=True,
)

# Only celery-beat actually schedules this (booking's other Celery
# container, celery-worker, just executes whatever it's told) — design
# §13's "nightly Celery job" for the audit hash chain's second layer.
# 2am PKT, per the timezone set above.
celery_app.conf.beat_schedule = {
    "verify-audit-chain-nightly": {
        "task": "booking.verify_audit_chain_task",
        "schedule": crontab(hour=2, minute=0),
    },
}

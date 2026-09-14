from __future__ import annotations

import logging

import httpx

from app.celery_app import celery_app
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@celery_app.task(name="booking.verify_audit_chain_task")
def verify_audit_chain_task() -> dict | None:
    """Nightly second layer for audit integrity (design §13). The
    DB-level INSERT-only grant on audit_log (deploy/postgres/audit-grants.sql)
    PREVENTS tampering; this DETECTS it independently, by asking audit's
    own /audit/verify to recompute every row's hash from scratch and
    compare against what's stored. A mismatch here would mean that
    DB-level protection was somehow bypassed (or a bug corrupted a row) —
    worth waking someone up for, which is why it's logged at CRITICAL
    ("PAGE:") rather than plain ERROR. No real paging service is wired up
    in this project (same honesty as notification/calendar-sync's stubs)
    — this log line is the stand-in a real on-call integration would
    replace."""
    settings = get_settings()
    try:
        response = httpx.get(f"{settings.audit_base_url}/audit/verify", timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # Audit being unreachable is an infra problem, not evidence of
        # tampering — logged distinctly so it's never confused with an
        # actual broken chain by whatever's watching these logs.
        logger.error("could not reach audit service to verify hash chain: %s", exc)
        return None

    result = response.json()
    if not result["valid"]:
        logger.critical(
            "PAGE: audit hash chain broken at row %s (checked %s rows)",
            result["broken_at_id"],
            result["rows_checked"],
        )
    else:
        logger.info("audit hash chain verified clean (%s rows)", result["rows_checked"])
    return result

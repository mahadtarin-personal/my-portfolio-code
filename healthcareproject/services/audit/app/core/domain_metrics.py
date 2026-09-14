from __future__ import annotations

import time

from app.crud.audit_log import verify_chain
from app.db.session import SessionLocal

_TTL_SECONDS = 60.0
_cache: dict[str, float] = {}


def compute_chain_status_metrics() -> dict[str, tuple[str, float]]:
    """Full-chain verification (verify_chain) re-hashes every row — cheap
    today, but it's an O(rows) job on the audit log's entire history, and
    Prometheus scrapes every 15s (deploy/prometheus/prometheus.yml). Rerun
    it at most once per _TTL_SECONDS regardless of scrape frequency; a
    scrape inside the window just serves the last result. Process-local
    cache (module dict) — fine for a single-instance service like this
    one, not safe to assume across multiple replicas."""
    now = time.monotonic()
    if now - _cache.get("computed_at", -_TTL_SECONDS) >= _TTL_SECONDS:
        with SessionLocal() as db:
            valid, _broken_at_id, rows_checked = verify_chain(db)
        _cache["valid"] = 1.0 if valid else 0.0
        _cache["rows_checked"] = float(rows_checked)
        _cache["computed_at"] = now

    return {
        "smarthealth_audit_chain_valid": (
            "1 if the audit hash chain verified intact as of the last check, else 0",
            _cache["valid"],
        ),
        "smarthealth_audit_chain_rows_checked": (
            "Row count covered by the last chain verification",
            _cache["rows_checked"],
        ),
    }

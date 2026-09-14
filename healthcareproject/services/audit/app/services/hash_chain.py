from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

GENESIS_HASH = "0" * 64


def _as_utc(value: datetime) -> datetime:
    """SQLite (tests) returns naive datetimes; Postgres returns
    timezone-aware ones. Both are semantically UTC in this app — normalize
    before hashing, same fix already applied in booking's
    services/slot_generation.py, otherwise recomputing a hash on a row
    freshly loaded from the DB would never match the one computed at
    insert time, and every row would look tampered with."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def compute_hash(
    prev_hash: str, event_type: str, actor: str | None, payload: dict, created_at: datetime
) -> str:
    """Deterministic — same inputs always produce the same hash, which is
    what makes verify_chain() able to recompute and compare rather than
    trust whatever's stored. json.dumps(sort_keys=True) so dict key order
    (which isn't semantically meaningful) never changes the hash."""
    material = "|".join(
        [
            prev_hash,
            event_type,
            actor or "",
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            _as_utc(created_at).isoformat(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

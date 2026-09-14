from __future__ import annotations

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address


def create_limiter() -> Limiter:
    """Keyed by client IP (get_remote_address) — the standard choice for
    brute-force protection on auth endpoints, where the attacker doesn't
    have a valid credential yet to key on anything more specific (a
    patient/user id). In-memory storage (slowapi's default, no storage_uri
    given) — per-process, resets on restart, doesn't coordinate across
    replicas. Matches this project's actual deployment shape (one
    instance per service, no HA) rather than adding a Redis dependency
    the four non-Redis services don't otherwise need; would need
    Redis/memcached-backed storage (storage_uri=...) before this could
    mean anything under multiple replicas."""
    return Limiter(key_func=get_remote_address)


def install_rate_limiting(app: FastAPI, limiter: Limiter) -> None:
    """Wires a Limiter into a FastAPI app — call once, in create_app(),
    before adding routers. Three things slowapi actually needs to work:
    app.state.limiter (what @limiter.limit(...) reads), the exception
    handler (turns a hit limit into a real 429 response instead of an
    unhandled exception), and the middleware (adds Retry-After/X-RateLimit
    response headers so a client can tell it was throttled, not just that
    something failed)."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

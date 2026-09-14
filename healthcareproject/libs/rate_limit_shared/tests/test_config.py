from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from rate_limit_shared import create_limiter, install_rate_limiting


def _make_app() -> FastAPI:
    app = FastAPI()
    limiter = create_limiter()
    install_rate_limiting(app, limiter)

    @app.get("/limited")
    @limiter.limit("2/minute")
    def limited(request: Request) -> dict:
        return {"ok": True}

    @app.get("/unlimited")
    def unlimited() -> dict:
        return {"ok": True}

    return app


def test_requests_within_the_limit_succeed() -> None:
    client = TestClient(_make_app())
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200


def test_exceeding_the_limit_returns_429() -> None:
    client = TestClient(_make_app())
    client.get("/limited")
    client.get("/limited")
    response = client.get("/limited")
    assert response.status_code == 429


def test_an_unlimited_route_is_unaffected_by_a_limited_ones_throttling() -> None:
    client = TestClient(_make_app())
    for _ in range(5):
        client.get("/limited")
    # /limited is now throttled, but a route with no @limiter.limit(...)
    # decorator was never subject to it in the first place.
    assert client.get("/unlimited").status_code == 200

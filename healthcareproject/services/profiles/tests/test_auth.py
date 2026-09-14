from fastapi.testclient import TestClient
from jwt_shared import decode_access_token

from app.core.config import get_settings
from app.main import app

PATIENT_PAYLOAD = {
    "name": "Bilal Ahmed",
    "email": "bilal@example.com",
    "phone": "+92-300-1111111",
    "password": "correct-password",
}


def test_login_with_wrong_password_is_rejected(client: TestClient) -> None:
    client.post("/patients", json=PATIENT_PAYLOAD)
    response = client.post(
        "/auth/login", json={"email": PATIENT_PAYLOAD["email"], "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_with_unknown_email_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )
    assert response.status_code == 401


def test_successful_login_returns_token(client: TestClient) -> None:
    client.post("/patients", json=PATIENT_PAYLOAD)
    response = client.post(
        "/auth/login", json={"email": PATIENT_PAYLOAD["email"], "password": PATIENT_PAYLOAD["password"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_successful_login_publishes_user_logged_in_event(client: TestClient, monkeypatch) -> None:
    from kafka_shared import Topic

    calls = []
    monkeypatch.setattr(
        "app.routers.auth.publish",
        lambda db, event_type, payload, *, actor=None: calls.append((event_type, payload, actor)),
    )

    registered = client.post("/patients", json=PATIENT_PAYLOAD).json()
    client.post(
        "/auth/login", json={"email": PATIENT_PAYLOAD["email"], "password": PATIENT_PAYLOAD["password"]}
    )

    assert len(calls) == 1
    event_type, payload, actor = calls[0]
    assert event_type == Topic.USER_LOGGED_IN
    assert payload == {"user_id": registered["id"]}
    assert actor == registered["id"]


def test_failed_login_publishes_user_login_failed_event(client: TestClient, monkeypatch) -> None:
    from kafka_shared import Topic

    calls = []
    monkeypatch.setattr(
        "app.routers.auth.publish",
        lambda db, event_type, payload, *, actor=None: calls.append((event_type, payload, actor)),
    )

    client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )

    assert len(calls) == 1
    event_type, payload, actor = calls[0]
    assert event_type == Topic.USER_LOGIN_FAILED
    assert payload == {"email": "nobody@example.com"}
    assert actor == "nobody@example.com"


def test_login_is_rate_limited_after_10_attempts_per_minute(client: TestClient) -> None:
    # app.state.limiter's storage is shared across every test in this
    # process (one app instance, imported once at module level) — reset
    # before AND after: before, because earlier tests in this file already
    # spent part of the budget on their own /auth/login calls; after (in a
    # finally), so exhausting the budget here can't bleed into any other
    # test that also calls /auth/login.
    app.state.limiter.reset()
    try:
        for _ in range(10):
            response = client.post(
                "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
            )
            assert response.status_code == 401  # within budget, rejected on credentials only

        throttled = client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
        )
        assert throttled.status_code == 429
    finally:
        app.state.limiter.reset()


# ---- POST /auth/service-token ----


def test_service_token_requires_the_correct_secret(client: TestClient) -> None:
    response = client.post(
        "/auth/service-token",
        json={"service_name": "booking"},
        headers={"X-Service-Secret": "wrong-secret"},
    )
    assert response.status_code == 401


def test_service_token_requires_the_header_at_all(client: TestClient) -> None:
    response = client.post("/auth/service-token", json={"service_name": "booking"})
    assert response.status_code == 422  # FastAPI's own missing-header rejection


def test_service_token_issues_a_real_admin_token(client: TestClient) -> None:
    settings = get_settings()
    response = client.post(
        "/auth/service-token",
        json={"service_name": "booking"},
        headers={"X-Service-Secret": settings.service_auth_secret},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    payload = decode_access_token(
        token, secret=settings.jwt_public_key_pem, algorithm=settings.jwt_algorithm
    )
    assert payload.sub == "booking"
    assert payload.role == "admin"
    # Same short-lived contract the old self-minted token had.
    assert payload.exp - payload.iat <= 5 * 60

from fastapi.testclient import TestClient
from jwt_shared import Role

from tests.conftest import auth_header

PATIENT_PAYLOAD = {
    "name": "Aisha Khan",
    "email": "aisha@example.com",
    "phone": "+92-300-0000000",
    "password": "s3cret-pass",
}


def test_register_patient_succeeds(client: TestClient) -> None:
    response = client.post("/patients", json=PATIENT_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == PATIENT_PAYLOAD["email"]
    assert "password" not in body


def test_register_patient_publishes_patient_registered_event(client: TestClient, monkeypatch) -> None:
    from kafka_shared import Topic

    calls = []
    monkeypatch.setattr(
        "app.routers.patients.publish",
        lambda db, event_type, payload, *, actor=None: calls.append((event_type, payload, actor)),
    )

    response = client.post("/patients", json=PATIENT_PAYLOAD)
    patient_id = response.json()["id"]

    assert len(calls) == 1
    event_type, payload, actor = calls[0]
    assert event_type == Topic.PATIENT_REGISTERED
    assert payload == {"patient_id": patient_id, "registered_by": "self"}
    assert actor == patient_id


def test_register_patient_can_then_log_in(client: TestClient) -> None:
    client.post("/patients", json=PATIENT_PAYLOAD)
    response = client.post(
        "/auth/login",
        json={"email": PATIENT_PAYLOAD["email"], "password": PATIENT_PAYLOAD["password"]},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_register_patient_duplicate_email_conflicts(client: TestClient) -> None:
    client.post("/patients", json=PATIENT_PAYLOAD)
    response = client.post("/patients", json=PATIENT_PAYLOAD)
    assert response.status_code == 409


def test_get_patient_requires_auth(client: TestClient) -> None:
    created = client.post("/patients", json=PATIENT_PAYLOAD).json()
    response = client.get(f"/patients/{created['id']}")
    assert response.status_code == 401  # HTTPBearer rejects the missing credentials


def test_patient_can_read_own_profile(client: TestClient) -> None:
    created = client.post("/patients", json=PATIENT_PAYLOAD).json()
    headers = auth_header(created["id"], Role.PATIENT)
    response = client.get(f"/patients/{created['id']}", headers=headers)
    assert response.status_code == 200


def test_patient_cannot_read_other_patient_profile(client: TestClient) -> None:
    created = client.post("/patients", json=PATIENT_PAYLOAD).json()
    other = client.post(
        "/patients",
        json={**PATIENT_PAYLOAD, "email": "other@example.com"},
    ).json()
    headers = auth_header(other["id"], Role.PATIENT)
    response = client.get(f"/patients/{created['id']}", headers=headers)
    assert response.status_code == 403


def test_admin_can_read_any_patient_profile(client: TestClient) -> None:
    created = client.post("/patients", json=PATIENT_PAYLOAD).json()
    headers = auth_header("admin-1", Role.ADMIN)
    response = client.get(f"/patients/{created['id']}", headers=headers)
    assert response.status_code == 200

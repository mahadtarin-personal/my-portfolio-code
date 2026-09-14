from fastapi.testclient import TestClient
from jwt_shared import Role

from tests.conftest import auth_header

STAFF_PAYLOAD = {
    "email": "frontdesk@medinova.example",
    "password": "front-desk-pass",
    "role": "front_desk",
}


def test_create_staff_user_requires_admin(client: TestClient) -> None:
    headers = auth_header("provider-1", Role.PROVIDER)
    response = client.post("/staff", json=STAFF_PAYLOAD, headers=headers)
    assert response.status_code == 403


def test_admin_can_create_staff_user(client: TestClient) -> None:
    headers = auth_header("admin-1", Role.ADMIN)
    response = client.post("/staff", json=STAFF_PAYLOAD, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "front_desk"
    assert "password" not in body


def test_new_staff_user_can_log_in(client: TestClient) -> None:
    headers = auth_header("admin-1", Role.ADMIN)
    client.post("/staff", json=STAFF_PAYLOAD, headers=headers)
    response = client.post(
        "/auth/login",
        json={"email": STAFF_PAYLOAD["email"], "password": STAFF_PAYLOAD["password"]},
    )
    assert response.status_code == 200

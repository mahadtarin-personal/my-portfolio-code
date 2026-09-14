from fastapi.testclient import TestClient
from jwt_shared import Role

from tests.conftest import auth_header

CLINIC_PAYLOAD = {
    "name": "MediNova North",
    "address": "123 Health Ave",
    "open_time": "09:00:00",
    "close_time": "17:00:00",
}


def test_create_clinic_requires_admin(client: TestClient) -> None:
    headers = auth_header("patient-1", Role.PATIENT)
    response = client.post("/clinics", json=CLINIC_PAYLOAD, headers=headers)
    assert response.status_code == 403


def test_admin_can_create_clinic(client: TestClient) -> None:
    headers = auth_header("admin-1", Role.ADMIN)
    response = client.post("/clinics", json=CLINIC_PAYLOAD, headers=headers)
    assert response.status_code == 201
    assert response.json()["name"] == CLINIC_PAYLOAD["name"]


def test_list_clinics_is_public(client: TestClient) -> None:
    headers = auth_header("admin-1", Role.ADMIN)
    client.post("/clinics", json=CLINIC_PAYLOAD, headers=headers)
    response = client.get("/clinics")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_duplicate_clinic_conflicts(client: TestClient) -> None:
    headers = auth_header("admin-1", Role.ADMIN)
    client.post("/clinics", json=CLINIC_PAYLOAD, headers=headers)
    response = client.post("/clinics", json=CLINIC_PAYLOAD, headers=headers)
    assert response.status_code == 409

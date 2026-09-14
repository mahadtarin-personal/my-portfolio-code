import httpx
from fastapi.testclient import TestClient
from jwt_shared import Role

from app.services.slot_reconciliation import trigger_slot_reconciliation
from tests.conftest import auth_header

CLINIC_PAYLOAD = {
    "name": "MediNova North",
    "address": "123 Health Ave",
    "open_time": "09:00:00",
    "close_time": "17:00:00",
}


def _register_clinic(client: TestClient) -> str:
    headers = auth_header("admin-1", Role.ADMIN)
    response = client.post("/clinics", json=CLINIC_PAYLOAD, headers=headers)
    return response.json()["id"]


def _provider_payload(clinic_id: str) -> dict:
    return {
        "clinic_id": clinic_id,
        "name": "Dr. Sara Khan",
        "specialty": "Cardiology",
        "license_number": "LIC-001",
        "consultation_fee": "50.00",
        "contact_email": "sara.khan@medinova.example",
        "contact_phone": "+92-300-2222222",
        "email": "sara.khan.login@medinova.example",
        "password": "provider-pass",
    }


def test_register_provider_requires_admin(client: TestClient) -> None:
    clinic_id = _register_clinic(client)
    headers = auth_header("patient-1", Role.PATIENT)
    response = client.post("/providers", json=_provider_payload(clinic_id), headers=headers)
    assert response.status_code == 403


def test_admin_can_register_provider(client: TestClient) -> None:
    clinic_id = _register_clinic(client)
    headers = auth_header("admin-1", Role.ADMIN)
    response = client.post("/providers", json=_provider_payload(clinic_id), headers=headers)
    assert response.status_code == 201
    assert response.json()["license_number"] == "LIC-001"


def test_provider_can_update_own_schedule(client: TestClient) -> None:
    clinic_id = _register_clinic(client)
    admin_headers = auth_header("admin-1", Role.ADMIN)
    provider = client.post(
        "/providers", json=_provider_payload(clinic_id), headers=admin_headers
    ).json()

    provider_headers = auth_header(provider["id"], Role.PROVIDER)
    schedule_payload = {
        "entries": [
            {
                "day_of_week": 0,
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "slot_duration_min": 20,
            }
        ]
    }
    response = client.put(
        f"/providers/{provider['id']}/schedule", json=schedule_payload, headers=provider_headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_other_provider_cannot_update_schedule(client: TestClient) -> None:
    clinic_id = _register_clinic(client)
    admin_headers = auth_header("admin-1", Role.ADMIN)
    provider = client.post(
        "/providers", json=_provider_payload(clinic_id), headers=admin_headers
    ).json()

    other_provider_headers = auth_header("some-other-provider-id", Role.PROVIDER)
    response = client.put(
        f"/providers/{provider['id']}/schedule",
        json={"entries": []},
        headers=other_provider_headers,
    )
    assert response.status_code == 403


def test_add_time_off_for_own_schedule(client: TestClient) -> None:
    clinic_id = _register_clinic(client)
    admin_headers = auth_header("admin-1", Role.ADMIN)
    provider = client.post(
        "/providers", json=_provider_payload(clinic_id), headers=admin_headers
    ).json()

    provider_headers = auth_header(provider["id"], Role.PROVIDER)
    response = client.post(
        f"/providers/{provider['id']}/time-off",
        json={"start_date": "2026-09-01", "end_date": "2026-09-05", "reason": "Leave"},
        headers=provider_headers,
    )
    assert response.status_code == 201
    assert response.json()["source"] == "manual"


def test_duplicate_time_off_conflicts(client: TestClient) -> None:
    clinic_id = _register_clinic(client)
    admin_headers = auth_header("admin-1", Role.ADMIN)
    provider = client.post(
        "/providers", json=_provider_payload(clinic_id), headers=admin_headers
    ).json()

    provider_headers = auth_header(provider["id"], Role.PROVIDER)
    payload = {"start_date": "2026-09-01", "end_date": "2026-09-05", "reason": "Leave"}
    client.post(f"/providers/{provider['id']}/time-off", json=payload, headers=provider_headers)
    response = client.post(
        f"/providers/{provider['id']}/time-off", json=payload, headers=provider_headers
    )
    assert response.status_code == 409


def test_duplicate_license_number_conflicts(client: TestClient) -> None:
    clinic_id = _register_clinic(client)
    admin_headers = auth_header("admin-1", Role.ADMIN)
    client.post("/providers", json=_provider_payload(clinic_id), headers=admin_headers)

    second_payload = {**_provider_payload(clinic_id), "email": "different.email@medinova.example"}
    response = client.post("/providers", json=second_payload, headers=admin_headers)
    assert response.status_code == 409


# ---- Slot reconciliation trigger (event-triggered Temporal reconcile in booking) ----


def _register_provider(client: TestClient) -> dict:
    clinic_id = _register_clinic(client)
    admin_headers = auth_header("admin-1", Role.ADMIN)
    return client.post("/providers", json=_provider_payload(clinic_id), headers=admin_headers).json()


def test_update_schedule_triggers_slot_reconciliation(client: TestClient, monkeypatch) -> None:
    provider = _register_provider(client)
    calls = []
    monkeypatch.setattr(
        "app.routers.providers.trigger_slot_reconciliation",
        lambda provider_id: calls.append(provider_id),
    )

    provider_headers = auth_header(provider["id"], Role.PROVIDER)
    schedule_payload = {
        "entries": [
            {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "slot_duration_min": 20}
        ]
    }
    response = client.put(
        f"/providers/{provider['id']}/schedule", json=schedule_payload, headers=provider_headers
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert str(calls[0]) == provider["id"]


def test_add_time_off_triggers_slot_reconciliation(client: TestClient, monkeypatch) -> None:
    provider = _register_provider(client)
    calls = []
    monkeypatch.setattr(
        "app.routers.providers.trigger_slot_reconciliation",
        lambda provider_id: calls.append(provider_id),
    )

    provider_headers = auth_header(provider["id"], Role.PROVIDER)
    response = client.post(
        f"/providers/{provider['id']}/time-off",
        json={"start_date": "2026-09-01", "end_date": "2026-09-05", "reason": "Leave"},
        headers=provider_headers,
    )

    assert response.status_code == 201
    assert len(calls) == 1
    assert str(calls[0]) == provider["id"]


def test_update_schedule_publishes_provider_schedule_changed_event(
    client: TestClient, monkeypatch
) -> None:
    from kafka_shared import Topic

    provider = _register_provider(client)
    calls = []
    monkeypatch.setattr(
        "app.routers.providers.publish",
        lambda db, event_type, payload, *, actor=None: calls.append((event_type, payload, actor)),
    )

    provider_headers = auth_header(provider["id"], Role.PROVIDER)
    schedule_payload = {
        "entries": [
            {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "slot_duration_min": 20}
        ]
    }
    client.put(f"/providers/{provider['id']}/schedule", json=schedule_payload, headers=provider_headers)

    assert len(calls) == 1
    event_type, payload, actor = calls[0]
    assert event_type == Topic.PROVIDER_SCHEDULE_CHANGED
    assert payload == {"provider_id": provider["id"], "reason": "schedule_updated"}
    assert actor == provider["id"]


def test_add_time_off_publishes_provider_schedule_changed_event(
    client: TestClient, monkeypatch
) -> None:
    from kafka_shared import Topic

    provider = _register_provider(client)
    calls = []
    monkeypatch.setattr(
        "app.routers.providers.publish",
        lambda db, event_type, payload, *, actor=None: calls.append((event_type, payload, actor)),
    )

    provider_headers = auth_header(provider["id"], Role.PROVIDER)
    client.post(
        f"/providers/{provider['id']}/time-off",
        json={"start_date": "2026-09-01", "end_date": "2026-09-05", "reason": "Leave"},
        headers=provider_headers,
    )

    assert len(calls) == 1
    event_type, payload, actor = calls[0]
    assert event_type == Topic.PROVIDER_SCHEDULE_CHANGED
    assert payload == {"provider_id": provider["id"], "reason": "time_off_added"}
    assert actor == provider["id"]


def test_get_schedule_requires_auth(client: TestClient) -> None:
    provider = _register_provider(client)
    response = client.get(f"/providers/{provider['id']}/schedule")
    assert response.status_code == 401  # HTTPBearer rejects the missing credentials


def test_get_schedule_rejects_unrelated_patient(client: TestClient) -> None:
    provider = _register_provider(client)
    other_headers = auth_header("some-patient-id", Role.PATIENT)
    response = client.get(f"/providers/{provider['id']}/schedule", headers=other_headers)
    assert response.status_code == 403


def test_get_schedule_allows_self_and_admin(client: TestClient) -> None:
    provider = _register_provider(client)
    provider_headers = auth_header(provider["id"], Role.PROVIDER)
    admin_headers = auth_header("admin-1", Role.ADMIN)

    assert client.get(f"/providers/{provider['id']}/schedule", headers=provider_headers).status_code == 200
    assert client.get(f"/providers/{provider['id']}/schedule", headers=admin_headers).status_code == 200


def test_list_time_off_requires_auth(client: TestClient) -> None:
    provider = _register_provider(client)
    response = client.get(f"/providers/{provider['id']}/time-off")
    assert response.status_code == 401


def test_slot_reconciliation_trigger_failure_does_not_break_schedule_update(
    client: TestClient, monkeypatch
) -> None:
    provider = _register_provider(client)

    def _raise(*args, **kwargs):
        raise httpx.ConnectError("booking unreachable")

    # conftest.py's autouse fixture no-ops the trigger for every other
    # test in this file — undo that here so the real fail-open path
    # (trigger_slot_reconciliation -> _post_reconcile -> httpx.post) is
    # actually exercised, with only the network call itself faked.
    monkeypatch.setattr(
        "app.routers.providers.trigger_slot_reconciliation", trigger_slot_reconciliation
    )
    monkeypatch.setattr("app.services.slot_reconciliation.httpx.post", _raise)

    provider_headers = auth_header(provider["id"], Role.PROVIDER)
    schedule_payload = {
        "entries": [
            {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "slot_duration_min": 20}
        ]
    }
    response = client.put(
        f"/providers/{provider['id']}/schedule", json=schedule_payload, headers=provider_headers
    )

    assert response.status_code == 200

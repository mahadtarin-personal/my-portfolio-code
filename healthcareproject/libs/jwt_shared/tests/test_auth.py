import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from jwt_shared import JWTAuth, Role, TokenPayload, create_access_token

SECRET = "test-secret"


@pytest.fixture
def app() -> FastAPI:
    auth = JWTAuth(secret=SECRET)
    app = FastAPI()

    @app.get("/whoami")
    def whoami(payload: TokenPayload = Depends(auth)) -> dict[str, str]:
        return {"sub": payload.sub, "role": payload.role}

    @app.get("/admin-only")
    def admin_only(
        payload: TokenPayload = Depends(auth.require_roles(Role.ADMIN)),
    ) -> dict[str, str]:
        return {"sub": payload.sub}

    return app


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_rejects_missing_token(app: FastAPI) -> None:
    client = TestClient(app)
    response = client.get("/whoami")
    assert response.status_code == 401  # HTTPBearer's own rejection, no credentials provided


def test_rejects_invalid_token(app: FastAPI) -> None:
    client = TestClient(app)
    response = client.get("/whoami", headers=_bearer("not-a-real-token"))
    assert response.status_code == 401


def test_accepts_valid_token(app: FastAPI) -> None:
    token = create_access_token(subject="patient-1", role=Role.PATIENT, secret=SECRET)
    client = TestClient(app)
    response = client.get("/whoami", headers=_bearer(token))
    assert response.status_code == 200
    assert response.json() == {"sub": "patient-1", "role": "patient"}


def test_require_roles_blocks_wrong_role(app: FastAPI) -> None:
    token = create_access_token(subject="patient-1", role=Role.PATIENT, secret=SECRET)
    client = TestClient(app)
    response = client.get("/admin-only", headers=_bearer(token))
    assert response.status_code == 403


def test_require_roles_allows_matching_role(app: FastAPI) -> None:
    token = create_access_token(subject="admin-1", role=Role.ADMIN, secret=SECRET)
    client = TestClient(app)
    response = client.get("/admin-only", headers=_bearer(token))
    assert response.status_code == 200

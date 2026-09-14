import os
import uuid
from collections.abc import Generator

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Test-only RSA keypair, generated fresh every test run — not a fixed key,
# nothing to leak. RS256 needs an actual keypair; a plain string secret
# like the old HS256 tests used won't decode.
_test_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_TEST_JWT_PRIVATE_KEY = _test_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
_TEST_JWT_PUBLIC_KEY = _test_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_PRIVATE_KEY", _TEST_JWT_PRIVATE_KEY)
os.environ.setdefault("JWT_PUBLIC_KEY", _TEST_JWT_PUBLIC_KEY)
os.environ.setdefault("SERVICE_AUTH_SECRET", "test-service-secret")
os.environ.setdefault("KAFKA_ENABLED", "false")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import pytest
from fastapi.testclient import TestClient
from jwt_shared import Role, create_access_token
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine, get_db
from app.main import app


@pytest.fixture(autouse=True)
def _schema() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _no_real_slot_reconciliation_trigger(monkeypatch) -> None:
    """update_schedule/add_time_off fire a background HTTP call to booking
    (see app/services/slot_reconciliation.py). booking doesn't exist in
    this test environment, so left unmocked every such test would eat the
    trigger's ~2s fail-open deadline for nothing. Tests that actually care
    about the trigger (test_providers.py) override this with their own
    monkeypatch."""
    monkeypatch.setattr("app.routers.providers.trigger_slot_reconciliation", lambda provider_id: None)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_header(subject: str | uuid.UUID, role: Role) -> dict[str, str]:
    settings = get_settings()
    token = create_access_token(
        subject=str(subject),
        role=role,
        secret=settings.jwt_private_key_pem,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}

import os
import uuid
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Test-only RSA keypair, generated fresh every test run — not a fixed
# key, nothing to leak. Booking's OWN Settings deliberately has no
# private key field at all in production (it only ever verifies, never
# signs) — but tests still need to mint synthetic tokens directly
# (auth_header() below) without going through a real profiles login, so
# the private half lives here as a module-level constant, used only by
# create_access_token() calls in this test suite.
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
os.environ.setdefault("JWT_PUBLIC_KEY", _TEST_JWT_PUBLIC_KEY)
os.environ.setdefault("SERVICE_AUTH_SECRET", "test-service-secret")
os.environ.setdefault("TEMPORAL_ENABLED", "false")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("KAFKA_ENABLED", "false")
os.environ.setdefault("GOOGLE_CALENDAR_ENABLED", "false")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import pytest
from fastapi.testclient import TestClient
from jwt_shared import Role, create_access_token
from sqlalchemy.orm import Session
from temporalio.exceptions import WorkflowAlreadyStartedError

from app import crud
from app.celery_app import celery_app
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine, get_db
from app.deps import get_temporal_client
from app.main import app
from app.models.slot import Slot

# Tests never talk to a real broker, same reasoning as REDIS_ENABLED/
# KAFKA_ENABLED above — eager mode runs a task's body inline, synchronously,
# the moment .delay() is called, so activities that enqueue Celery tasks
# (app.activities.booking.sync_calendar/revert_calendar_sync) behave the
# same in tests as they do against a real worker, without needing Redis up.
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True


class FakeTemporalClient:
    """Stand-in for the real Temporal Client in HTTP-level tests — these
    tests exercise POST /appointments' synchronous contract (create PENDING,
    claim idempotency, return 202) without a worker actually running the
    saga. The saga itself is tested directly in test_booking_saga.py via
    temporalio's time-skipping test environment."""

    def __init__(self) -> None:
        self.started: list[tuple] = []
        self.raise_already_started = False

    async def start_workflow(self, *args, **kwargs):
        if self.raise_already_started:
            raise WorkflowAlreadyStartedError(kwargs.get("id", ""), args[0].__qualname__)
        self.started.append((args, kwargs))


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


@pytest.fixture
def fake_temporal_client() -> FakeTemporalClient:
    """One instance per test, reused across every request in that test —
    lets a test assert on `.started` after making several calls (e.g.
    book, then cancel, then check whether promotion started a workflow)."""
    return FakeTemporalClient()


@pytest.fixture
def client(fake_temporal_client: FakeTemporalClient) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_temporal_client] = lambda: fake_temporal_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_header(subject: str | uuid.UUID, role: Role) -> dict[str, str]:
    settings = get_settings()
    # Signed directly with the test-only private key (above), NOT
    # anything from settings — booking's own Settings has no private key
    # field at all in production, by design (it never signs a token,
    # only verifies). settings.jwt_public_key_pem just needs to match
    # this key's public half, which it does (same test keypair).
    token = create_access_token(
        subject=str(subject),
        role=role,
        secret=_TEST_JWT_PRIVATE_KEY,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def open_slot(db: Session) -> Slot:
    provider_id = uuid.uuid4()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = crud.slot.create(
        db, provider_id=provider_id, start_time=start, end_time=start + timedelta(minutes=20)
    )
    db.commit()
    return slot

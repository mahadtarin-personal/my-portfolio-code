import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from jwt_shared import Role, create_access_token
from kafka_shared import Topic
from sqlalchemy.orm import Session

from app import crud
from app.core.config import get_settings
from app.db.session import get_db
from app.deps import limiter
from app.schemas.auth import LoginRequest, ServiceTokenRequest, TokenResponse
from app.services.events import publish

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = crud.user.authenticate(db, email=payload.email, password=payload.password)
    if user is None:
        publish(db, Topic.USER_LOGIN_FAILED, {"email": payload.email}, actor=payload.email)
        db.commit()  # outbox row — login itself writes nothing else here
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    subject = str(user.patient_id or user.provider_id or user.id)
    token = create_access_token(
        subject=subject,
        role=user.role,
        secret=settings.jwt_private_key_pem,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_expires_minutes,
    )
    publish(db, Topic.USER_LOGGED_IN, {"user_id": subject}, actor=subject)
    db.commit()  # outbox row — login itself writes nothing else here
    return TokenResponse(access_token=token)


@router.post("/service-token", response_model=TokenResponse)
def issue_service_token(
    payload: ServiceTokenRequest,
    x_service_secret: str = Header(alias="X-Service-Secret"),
) -> TokenResponse:
    """Replaces the old self-minted service credential (booking used to
    sign its own admin token with the shared JWT_SECRET — under RS256 it
    has no signing key to do that with at all, by design). A service
    proves it belongs on the network with a separate, narrow-purpose
    shared secret (never the RSA keys — this can be rotated on its own
    without touching user-token signing), and profiles issues a real,
    properly-signed short-lived credential in response.

    secrets.compare_digest — a plain `==` on the secret would leak timing
    information about how many leading characters matched, same reasoning
    as comparing a password hash rather than a raw password."""
    if not secrets.compare_digest(x_service_secret, settings.service_auth_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service secret")
    token = create_access_token(
        subject=payload.service_name,
        role=Role.ADMIN,
        secret=settings.jwt_private_key_pem,
        algorithm=settings.jwt_algorithm,
        expires_minutes=5,
    )
    return TokenResponse(access_token=token)

import uuid

from fastapi import HTTPException, status
from jwt_shared import JWTAuth, Role, TokenPayload
from rate_limit_shared import create_limiter

from app.core.config import get_settings

settings = get_settings()
# Verification always uses the PUBLIC key, even here in the service that
# also holds the private one — profiles never needs the private key to
# check a token it's just reading, only to mint a new one (see auth.py).
auth = JWTAuth(secret=settings.jwt_public_key_pem, algorithm=settings.jwt_algorithm)
limiter = create_limiter()


def ensure_self_or_roles(
    payload: TokenPayload, resource_id: uuid.UUID, *roles: Role | str
) -> None:
    """Authorizes a request against a specific patient/provider record: the
    token's own subject always passes (acting on your own record), otherwise
    the caller's role must be one of `roles` (e.g. admin, front_desk)."""
    if payload.sub == str(resource_id):
        return
    allowed = {r.value if isinstance(r, Role) else r for r in roles}
    if payload.role in allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not authorized for this resource",
    )

from __future__ import annotations

import time
import uuid

import jwt
from pydantic import BaseModel

from .roles import Role


class TokenPayload(BaseModel):
    """`sub` is the owning domain id — a patient_id or provider_id for those
    roles, or the users.id for front_desk/admin, who have no domain record
    of their own. Booking authorizes against this without ever calling
    Profiles.

    `jti` (JWT ID) identifies THIS specific token, distinct from `sub`
    (which identifies the user) — two tokens issued to the same user carry
    different `jti` values. It exists so a single compromised token can be
    revoked without invalidating every token for that user or rotating the
    shared signing key (which would log everyone out). No revocation list
    is wired up yet — this only adds the identifier a future one would
    check against.

    `iat` (issued-at, Unix timestamp) is when the token was minted, not
    when it expires. It's what lets a security response like "everything
    issued before this password change is now invalid" be expressed at
    all — without it there's no way to reason about a token's age
    independent of `exp`."""

    sub: str
    role: str
    exp: int
    jti: str
    iat: int


def create_access_token(
    *,
    subject: str,
    role: Role | str,
    secret: str,
    algorithm: str = "HS256",
    expires_minutes: int = 60,
) -> str:
    role_value = role.value if isinstance(role, Role) else role
    now = int(time.time())
    payload = {
        "sub": subject,
        "role": role_value,
        "exp": now + expires_minutes * 60,
        "jti": str(uuid.uuid4()),
        "iat": now,
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, *, secret: str, algorithm: str = "HS256") -> TokenPayload:
    payload = jwt.decode(token, secret, algorithms=[algorithm])
    return TokenPayload(**payload)

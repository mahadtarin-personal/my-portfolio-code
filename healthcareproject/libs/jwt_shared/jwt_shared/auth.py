from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .roles import Role
from .tokens import TokenPayload, decode_access_token

_bearer_scheme = HTTPBearer()


class JWTAuth:
    """Stateless bearer-token verification, callable as a FastAPI dependency.

    Each service instantiates its own `JWTAuth(secret=..., algorithm=...)`
    from its own settings — the same JWT_SECRET is shared across services so
    a token issued by Profiles' /auth/login is independently verifiable by
    Booking without a network call back to Profiles.
    """

    def __init__(self, *, secret: str, algorithm: str = "HS256") -> None:
        self._secret = secret
        self._algorithm = algorithm

    async def __call__(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    ) -> TokenPayload:
        try:
            return decode_access_token(
                credentials.credentials, secret=self._secret, algorithm=self._algorithm
            )
        except pyjwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            ) from exc

    def require_roles(
        self, *roles: Role | str
    ) -> Callable[..., Coroutine[Any, Any, TokenPayload]]:
        allowed = {r.value if isinstance(r, Role) else r for r in roles}

        async def _dependency(payload: TokenPayload = Depends(self)) -> TokenPayload:
            if allowed and payload.role not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient role for this operation",
                )
            return payload

        return _dependency

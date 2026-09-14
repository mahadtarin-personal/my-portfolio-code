from fastapi import Request
from jwt_shared import JWTAuth
from rate_limit_shared import create_limiter
from temporalio.client import Client

from app.core.config import get_settings

settings = get_settings()
auth = JWTAuth(secret=settings.jwt_public_key_pem, algorithm=settings.jwt_algorithm)
limiter = create_limiter()


def get_temporal_client(request: Request) -> Client:
    return request.app.state.temporal_client

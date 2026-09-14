from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ServiceTokenRequest(BaseModel):
    """service_name becomes the token's `sub` — an audit trail of which
    service asked for a credential, not a real identity check (the
    X-Service-Secret header is what actually authenticates the request;
    this is just a label)."""

    service_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

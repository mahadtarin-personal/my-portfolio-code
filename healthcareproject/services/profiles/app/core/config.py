from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    # RS256: profiles is the only service that ever SIGNS a token (user
    # login here, or a service-token grant via POST /auth/service-token)
    # so it's the only one that needs the private key at all. Every
    # service, profiles included, needs the public key to VERIFY. Stored
    # \n-escaped in the env (a real PEM has literal newlines, which don't
    # survive a single-line env var/--env-file entry) -- see the
    # jwt_*_key_pem properties below for the unescaped form actually
    # handed to jwt_shared.
    jwt_private_key: str = ""
    jwt_public_key: str
    jwt_algorithm: str = "RS256"
    jwt_expires_minutes: int = 60
    # Pre-shared secret authenticating POST /auth/service-token requests —
    # deliberately NOT the RSA keys: a service asking to be issued a real
    # token proves it belongs on the network with this, it never gets
    # anything that could itself sign a token.
    service_auth_secret: str
    booking_base_url: str = "http://booking:8000"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @property
    def jwt_private_key_pem(self) -> str:
        return self.jwt_private_key.replace("\\n", "\n")

    @property
    def jwt_public_key_pem(self) -> str:
        return self.jwt_public_key.replace("\\n", "\n")


@lru_cache
def get_settings() -> Settings:
    return Settings()

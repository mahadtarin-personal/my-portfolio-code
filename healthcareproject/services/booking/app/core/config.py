from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    # RS256: booking only ever VERIFIES tokens, never signs one -- it has
    # no private key at all, unlike profiles. \n-escaped in the env, same
    # reasoning as profiles' Settings (see jwt_public_key_pem below).
    jwt_public_key: str
    jwt_algorithm: str = "RS256"
    # Pre-shared secret for POST /auth/service-token — this REPLACES
    # self-minting an admin token with the old shared JWT_SECRET
    # (app/services/slot_generation.py used to do exactly that, which
    # meant any service holding the secret could forge an admin
    # credential for itself; under RS256 booking has no signing key to
    # forge one with in the first place, so it has to actually ask
    # profiles for a real one, proven legitimate by this secret instead).
    service_auth_secret: str
    temporal_address: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "booking-saga"
    temporal_enabled: bool = True
    profiles_base_url: str = "http://profiles:8000"
    audit_base_url: str = "http://audit:8000"
    redis_url: str = "redis://redis:6379/0"
    redis_enabled: bool = True
    slots_cache_ttl_seconds: int = 60
    slots_cache_ttl_jitter_seconds: int = 15
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_enabled: bool = True

    # Real Google Calendar integration for sync_calendar_task — off by
    # default (falls back to the stub-only log+record behavior) since
    # most environments running this project won't have OAuth credentials
    # for a real Google account. See app/services/google_calendar.py.
    google_calendar_enabled: bool = False
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    google_calendar_refresh_token: str = ""
    google_calendar_id: str = "primary"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @property
    def jwt_public_key_pem(self) -> str:
        return self.jwt_public_key.replace("\\n", "\n")


@lru_cache
def get_settings() -> Settings:
    return Settings()

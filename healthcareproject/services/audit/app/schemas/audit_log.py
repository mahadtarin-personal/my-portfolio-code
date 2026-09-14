from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    event_type: str
    actor: str | None
    payload: dict
    prev_hash: str
    hash: str
    created_at: datetime


class VerifyResult(BaseModel):
    valid: bool
    broken_at_id: int | None = None
    rows_checked: int

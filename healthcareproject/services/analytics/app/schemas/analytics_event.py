import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AnalyticsEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: str
    event_type: str
    actor: str | None
    payload: dict
    created_at: datetime

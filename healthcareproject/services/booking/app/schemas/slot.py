import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.slot import SlotStatus


class SlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    start_time: datetime
    end_time: datetime
    status: SlotStatus

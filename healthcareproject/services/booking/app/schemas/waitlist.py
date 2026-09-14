import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.waitlist import WaitlistStatus


class WaitlistJoin(BaseModel):
    slot_id: uuid.UUID


class WaitlistEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    provider_id: uuid.UUID
    slot_id: uuid.UUID
    status: WaitlistStatus
    created_at: datetime

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.visit import VisitStatus


class VisitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    appointment_id: uuid.UUID
    status: VisitStatus
    checked_in_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

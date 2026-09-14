import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationChannel, NotificationStatus


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: str
    event_type: str
    recipient: str
    channel: NotificationChannel
    status: NotificationStatus
    message: str
    created_at: datetime

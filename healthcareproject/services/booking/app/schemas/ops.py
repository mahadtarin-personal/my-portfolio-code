import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.calendar_sync_log import CalendarSyncAction
from app.models.reminder_log import ReminderStatus


class CalendarSyncLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    appointment_id: uuid.UUID
    provider_id: uuid.UUID
    action: CalendarSyncAction
    external_event_id: str | None
    created_at: datetime


class ReminderLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    provider_id: uuid.UUID
    appointment_start_time: datetime
    status: ReminderStatus
    appointment_status: str
    created_at: datetime
    updated_at: datetime | None

import uuid
from datetime import date, time

from pydantic import BaseModel, ConfigDict

from app.models.schedule import DayOfWeek, TimeOffSource


class ProviderScheduleEntry(BaseModel):
    day_of_week: DayOfWeek
    start_time: time
    end_time: time
    slot_duration_min: int


class ProviderScheduleRead(ProviderScheduleEntry):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID


class ProviderScheduleUpdate(BaseModel):
    entries: list[ProviderScheduleEntry]


class TimeOffCreate(BaseModel):
    start_date: date
    end_date: date
    reason: str | None = None


class TimeOffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    start_date: date
    end_date: date
    reason: str | None
    source: TimeOffSource

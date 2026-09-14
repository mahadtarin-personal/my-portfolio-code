import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.appointment import AppointmentStatus


class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    provider_id: uuid.UUID
    slot_id: uuid.UUID


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    provider_id: uuid.UUID
    slot_id: uuid.UUID
    status: AppointmentStatus
    created_at: datetime


class AppointmentUpdate(BaseModel):
    """Only cancellation is supported here — rescheduling is its own
    endpoint (POST /appointments/{id}/reschedule), since it needs a target
    slot, not just a status flip."""

    status: AppointmentStatus


class RescheduleRequest(BaseModel):
    new_slot_id: uuid.UUID

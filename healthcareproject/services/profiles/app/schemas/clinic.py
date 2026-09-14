import uuid
from datetime import time

from pydantic import BaseModel, ConfigDict


class ClinicCreate(BaseModel):
    name: str
    address: str
    open_time: time
    close_time: time


class ClinicRead(ClinicCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID

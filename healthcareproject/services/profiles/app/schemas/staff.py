import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr


class StaffRole(str, Enum):
    """front_desk and admin accounts have no domain entity to attach to, so
    they're provisioned directly through this endpoint rather than through
    patient/provider registration."""

    FRONT_DESK = "front_desk"
    ADMIN = "admin"


class StaffUserCreate(BaseModel):
    email: EmailStr
    password: str
    role: StaffRole


class StaffUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: StaffRole

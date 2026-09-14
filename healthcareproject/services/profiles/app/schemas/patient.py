import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


class PatientRegister(BaseModel):
    name: str
    email: EmailStr
    phone: str
    password: str


class PatientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    phone: str

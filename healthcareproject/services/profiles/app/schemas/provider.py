import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr


class ProviderRegister(BaseModel):
    clinic_id: uuid.UUID
    name: str
    specialty: str
    license_number: str
    consultation_fee: Decimal
    contact_email: EmailStr
    contact_phone: str
    email: EmailStr
    password: str


class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    name: str
    specialty: str
    license_number: str
    consultation_fee: Decimal
    contact_email: EmailStr
    contact_phone: str

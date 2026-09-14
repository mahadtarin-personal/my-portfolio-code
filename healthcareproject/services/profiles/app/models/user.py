import uuid
from datetime import datetime, timezone

from jwt_shared import Role
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """Login credentials and role, kept separate from Patient/Provider since
    front_desk and admin have no domain record of their own — the ERD (§5.1)
    doesn't define an auth entity, so this is an addition to make RBAC
    (§3.1) actually implementable."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("patients.id"), unique=True, nullable=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("providers.id"), unique=True, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

import uuid

from jwt_shared import Role
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def create(
    db: Session,
    *,
    email: str,
    password: str,
    role: Role,
    patient_id: uuid.UUID | None = None,
    provider_id: uuid.UUID | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        role=role,
        patient_id=patient_id,
        provider_id=provider_id,
    )
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, *, email: str, password: str) -> User | None:
    user = get_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

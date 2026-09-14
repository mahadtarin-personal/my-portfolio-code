from fastapi import APIRouter, Depends, HTTPException, status
from jwt_shared import Role
from sqlalchemy.orm import Session

from app import crud
from app.db.session import get_db
from app.deps import auth
from app.schemas.staff import StaffUserCreate, StaffUserRead

router = APIRouter(prefix="/staff", tags=["staff"])


@router.post(
    "",
    response_model=StaffUserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_roles(Role.ADMIN))],
)
def create_staff_user(payload: StaffUserCreate, db: Session = Depends(get_db)) -> StaffUserRead:
    if crud.user.get_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = crud.user.create(
        db, email=payload.email, password=payload.password, role=Role(payload.role.value)
    )
    db.commit()
    return StaffUserRead(id=user.id, email=user.email, role=payload.role)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.dependencies.auth import get_current_user,require_roles
from app.models import User
from app.schemas import UserResponse
from app.schemas.user import UserUpdate, UserUpdateResponse
from app.database import get_db
from app.core.security import create_access_token


router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.get(
    "/admin-test"
)
def admin_test(
    current_user: User = Depends(
        require_roles("admin")
    )
):

    return {
        "message": "Acceso autorizado",
        "user": current_user.email,
        "role": current_user.role
    }

@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user)
):

    return current_user


@router.put("/me", response_model=UserUpdateResponse)
def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    changes = data.model_dump(exclude_unset=True)
    if "email" in changes:
        duplicate = db.query(User.id).filter(
            func.lower(User.email) == changes["email"].lower(),
            User.id != current_user.id,
        ).first()
        if duplicate:
            raise HTTPException(409, "El email ya esta registrado")
    # SQLAlchemy solo actualiza los campos proporcionados de la cuenta autenticada.
    for field, value in changes.items():
        setattr(current_user, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "El email ya esta registrado") from exc
    db.refresh(current_user)
    token = create_access_token({
        "sub": str(current_user.id), "email": current_user.email, "role": current_user.role,
    })
    return UserUpdateResponse(**UserResponse.model_validate(current_user).model_dump(), access_token=token)

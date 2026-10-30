from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user,require_roles
from app.models import User
from app.schemas import UserResponse
from app.schemas.user import UserUpdate, UserUpdateResponse
from app.database import get_db
from app.user_actions import update_profile


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
    return update_profile(db, current_user, data)

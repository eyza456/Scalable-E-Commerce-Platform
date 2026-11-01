from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user,require_roles
from app.models import User
from app.schemas import UserResponse
from app.schemas.user import AdminUserUpdate, UserUpdate, UserUpdateResponse
from app.database import get_db
from app.user_actions import update_profile, update_user_admin
from app.user_repository import find_by_id, list_users


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


@router.get("", response_model=list[UserResponse])
def list_all_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    if skip < 0 or limit < 1 or limit > 100:
        raise HTTPException(422, "Paginacion fuera de rango")
    return list_users(db, skip, limit)


@router.get("/{user_id}", response_model=UserResponse)
def get_user_admin(
    user_id: int,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    user = find_by_id(db, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user_admin_route(
    user_id: int,
    data: AdminUserUpdate,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    user = find_by_id(db, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    return update_user_admin(db, current_user, user, data)

"""Application actions for registration, authentication and profile updates."""

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import UserCreate, UserLogin, UserResponse
from app.schemas.user import AdminUserUpdate, UserUpdate, UserUpdateResponse
from app.user_repository import add_user, commit_user, find_by_email, find_duplicate_email


def register_user(db: Session, user_data: UserCreate) -> User:
    if find_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado",
        )

    user = add_user(
        db,
        User(
            name=user_data.name,
            email=user_data.email,
            password_hash=hash_password(user_data.password),
        ),
    )
    try:
        return commit_user(db, user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(400, "El email ya esta registrado") from exc


def authenticate_user(db: Session, user_data: UserLogin) -> dict[str, str]:
    user = find_by_email(db, user_data.email)
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario está desactivado",
        )
    return {
        "access_token": create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role}
        ),
        "token_type": "bearer",
    }


def update_profile(db: Session, current_user: User, data: UserUpdate) -> UserUpdateResponse:
    changes = data.model_dump(exclude_unset=True)
    if "email" in changes and find_duplicate_email(
        db, changes["email"], current_user.id
    ):
        raise HTTPException(409, "El email ya esta registrado")

    for field, value in changes.items():
        setattr(current_user, field, value)
    try:
        commit_user(db, current_user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "El email ya esta registrado") from exc

    token = create_access_token(
        {"sub": str(current_user.id), "email": current_user.email, "role": current_user.role}
    )
    return UserUpdateResponse(
        **UserResponse.model_validate(current_user).model_dump(),
        access_token=token,
    )


def update_user_admin(db: Session, current_user: User, target: User, data: AdminUserUpdate) -> User:
    changes = data.model_dump(exclude_unset=True)
    if target.id == current_user.id and (
        changes.get("role", target.role) != target.role
        or changes.get("is_active", target.is_active) is False
    ):
        raise HTTPException(409, "No puedes desactivar o cambiar tu propio rol")
    for field, value in changes.items():
        setattr(target, field, value)
    try:
        return commit_user(db, target)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "No se pudo actualizar el usuario") from exc


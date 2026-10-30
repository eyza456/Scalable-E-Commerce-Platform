"""Persistence queries for user-service.

This module owns SQLAlchemy access so route handlers and use cases do not
duplicate query details.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import User


def find_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(func.lower(User.email) == email.lower()).first()


def find_duplicate_email(db: Session, email: str, user_id: int) -> User | None:
    return (
        db.query(User.id)
        .filter(func.lower(User.email) == email.lower(), User.id != user_id)
        .first()
    )


def add_user(db: Session, user: User) -> User:
    db.add(user)
    return user


def commit_user(db: Session, user: User) -> User:
    db.commit()
    db.refresh(user)
    return user


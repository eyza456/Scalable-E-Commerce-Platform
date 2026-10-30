"""Application actions for catalog category management."""

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.category_repository import (
    add_category,
    delete_category_row,
    get_category,
    has_products,
    list_categories,
)
from app.models import Category
from app.schemas.category import CategoryCreate


def find_category(db: Session, category_id: int) -> Category:
    category = get_category(db, category_id)
    if category is None:
        raise HTTPException(404, "Categoria no encontrada")
    return category


def commit_category(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Nombre de categoria duplicado o categoria en uso") from exc


def read_categories(db: Session, skip: int, limit: int) -> list[Category]:
    return list_categories(db, skip, limit)


def create_category(db: Session, data: CategoryCreate) -> Category:
    category = add_category(db, Category(**data.model_dump()))
    commit_category(db)
    db.refresh(category)
    return category


def update_category(db: Session, category_id: int, data: CategoryCreate) -> Category:
    category = find_category(db, category_id)
    for field, value in data.model_dump().items():
        setattr(category, field, value)
    commit_category(db)
    db.refresh(category)
    return category


def remove_category(db: Session, category_id: int) -> None:
    category = find_category(db, category_id)
    if has_products(db, category_id):
        raise HTTPException(409, "Categoria asignada a productos; reasignarlos antes de eliminar")
    delete_category_row(db, category)
    commit_category(db)


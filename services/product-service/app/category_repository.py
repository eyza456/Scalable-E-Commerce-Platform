"""SQLAlchemy persistence helpers for catalog categories."""

from sqlalchemy.orm import Session

from app.models import Category, Product


def list_categories(db: Session, skip: int, limit: int) -> list[Category]:
    return db.query(Category).order_by(Category.id).offset(skip).limit(limit).all()


def get_category(db: Session, category_id: int) -> Category | None:
    return db.get(Category, category_id)


def has_products(db: Session, category_id: int) -> bool:
    return db.query(Product.id).filter_by(category_id=category_id).first() is not None


def add_category(db: Session, category: Category) -> Category:
    db.add(category)
    return category


def delete_category_row(db: Session, category: Category) -> None:
    db.delete(category)


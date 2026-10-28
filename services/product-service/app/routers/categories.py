from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_roles
from app.database import get_db
from app.models import Category, Product
from app.schemas.category import CategoryCreate, CategoryResponse

router = APIRouter(prefix="/categories", tags=["Categories"])
admin = Depends(require_roles("admin"))


def find_category(db, category_id):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(404, "Categoria no encontrada")
    return category


def commit_category(db):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Nombre de categoria duplicado o categoria en uso") from exc


@router.get("", response_model=list[CategoryResponse])
def list_categories(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100), db: Session = Depends(get_db)):
    return db.query(Category).order_by(Category.id).offset(skip).limit(limit).all()


@router.get("/{category_id}", response_model=CategoryResponse)
def read_category(category_id: int, db: Session = Depends(get_db)):
    return find_category(db, category_id)


@router.post("", response_model=CategoryResponse, status_code=201)
def create_category(data: CategoryCreate, db: Session = Depends(get_db), current_user=admin):
    category = Category(**data.model_dump())
    db.add(category)
    commit_category(db)
    db.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, data: CategoryCreate, db: Session = Depends(get_db), current_user=admin):
    category = find_category(db, category_id)
    for field, value in data.model_dump().items():
        setattr(category, field, value)
    commit_category(db)
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db), current_user=admin):
    category = find_category(db, category_id)
    if db.query(Product.id).filter_by(category_id=category_id).first():
        raise HTTPException(409, "Categoria asignada a productos; reasignarlos antes de eliminar")
    db.delete(category)
    commit_category(db)
    return Response(status_code=204)

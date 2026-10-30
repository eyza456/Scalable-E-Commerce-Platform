from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.security import require_roles
from app.database import get_db
from app.models import Category
from app.schemas.category import CategoryCreate, CategoryResponse
from app.category_actions import (
    commit_category,
    create_category as create_category_action,
    find_category,
    read_categories,
    remove_category,
    update_category as update_category_action,
)

router = APIRouter(prefix="/categories", tags=["Categories"])
admin = Depends(require_roles("admin"))


@router.get("", response_model=list[CategoryResponse])
def list_categories(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100), db: Session = Depends(get_db)):
    return read_categories(db, skip, limit)


@router.get("/{category_id}", response_model=CategoryResponse)
def read_category(category_id: int, db: Session = Depends(get_db)):
    return find_category(db, category_id)


@router.post("", response_model=CategoryResponse, status_code=201)
def create_category(data: CategoryCreate, db: Session = Depends(get_db), current_user=admin):
    return create_category_action(db, data)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, data: CategoryCreate, db: Session = Depends(get_db), current_user=admin):
    return update_category_action(db, category_id, data)


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db), current_user=admin):
    remove_category(db, category_id)
    return Response(status_code=204)

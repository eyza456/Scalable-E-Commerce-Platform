from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models import Product, Category, InventoryReservation
from sqlalchemy.dialects.postgresql import JSONB
from app.schemas import ProductCreate, ProductUpdate


def resolve_category(db, data):
    if "category" in data:
        name = data.pop("category")
        if name is None:
            data["category_id"] = None
        else:
            category = db.query(Category).filter(func.lower(Category.name) == name.strip().lower()).first()
            if category is None:
                raise HTTPException(404, "Categoria no encontrada; crearla antes de asignarla")
            data["category_id"] = category.id
    if data.get("category_id") is not None:
        if db.get(Category, data["category_id"]) is None:
            raise HTTPException(404, "Categoria no encontrada")
    return data


def commit_product(db):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "El producto entra en conflicto con los datos actuales") from exc


def create_product(
    db: Session,
    product_data: ProductCreate
) -> Product:

    new_product = Product(**resolve_category(db, product_data.model_dump(exclude_unset=True)))

    db.add(new_product)
    commit_product(db)
    db.refresh(new_product)

    return new_product


def get_products(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    name: str | None = None,
    category_id: int | None = None,
    available: bool | None = None,
):

    query = db.query(Product)
    if name is not None:
        term = name.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(Product.name.ilike(f"%{term}%", escape="\\"))
    if category_id is not None:
        query = query.filter(Product.category_id == category_id)
    if available is not None:
        availability = and_(Product.is_active.is_(True), Product.stock > 0)
        query = query.filter(availability if available else ~availability)
    return (
        query.order_by(Product.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_product_by_id(
    db: Session,
    product_id: int
):

    return (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )


def update_product(
    db: Session,
    product: Product,
    product_data: ProductUpdate
) -> Product:

    update_data = resolve_category(db, product_data.model_dump(
        exclude_unset=True
    ))

    for field, value in update_data.items():
        setattr(product, field, value)

    commit_product(db)
    db.refresh(product)

    return product


def delete_product(
    db: Session,
    product: Product
) -> None:
    product = db.query(Product).filter_by(id=product.id).with_for_update(of=Product).populate_existing().first()
    if product is None:
        raise HTTPException(404, "Producto no encontrado")
    if db.query(InventoryReservation.transaction_id).filter(
        InventoryReservation.status == "RESERVED",
        InventoryReservation.items.cast(JSONB).contains([{"product_id": product.id}]),
    ).first():
        raise HTTPException(409, "El producto tiene reservas pendientes")
    db.delete(product)
    db.commit()

"""Application actions that do not belong in product route handlers."""

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.crud import get_product_by_id
from app.models import Product
from app.schemas import StockDecrease


def decrease_stock(db: Session, product_id: int, stock_data: StockDecrease) -> Product:
    product = get_product_by_id(db=db, product_id=product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    result = db.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock >= stock_data.quantity)
        .values(stock=Product.stock - stock_data.quantity)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stock insuficiente")
    db.commit()
    db.refresh(product)
    return product


from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.models import Product
from app.core.security import require_roles
from app.schemas import StockDecrease

from app.crud import (
    create_product,
    delete_product,
    get_product_by_id,
    get_products,
    update_product
)
from app.database import get_db
from app.schemas import (
    ProductCreate,
    ProductResponse,
    ProductUpdate
)
from app.product_actions import decrease_stock


router = APIRouter(
    prefix="/products",
    tags=["Products"]
)

@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED
)
def create_new_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_roles("admin", "seller")
    )
):
    return create_product(
        db=db,
        product_data=product_data
    )


@router.get(
    "/",
    response_model=list[ProductResponse]
)
def read_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    name: str | None = Query(None, min_length=1, max_length=150),
    category_id: int | None = Query(None, gt=0),
    available: bool | None = None,
    db: Session = Depends(get_db)
):

    return get_products(
        db=db,
        skip=skip,
        limit=limit,
        name=name,
        category_id=category_id,
        available=available,
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse
)
def read_product(
    product_id: int,
    db: Session = Depends(get_db)
):

    product = get_product_by_id(
        db=db,
        product_id=product_id
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )

    return product


@router.put(
    "/{product_id}",
    response_model=ProductResponse
)
def update_existing_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_roles("admin", "seller")
    )
):

    product = get_product_by_id(
        db=db,
        product_id=product_id
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )

    return update_product(
        db=db,
        product=product,
        product_data=product_data
    )


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_existing_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_roles("admin", "seller")
    )
):

    product = get_product_by_id(
        db=db,
        product_id=product_id
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )

    delete_product(
        db=db,
        product=product
    )

    return None

@router.patch(
    "/{product_id}/stock/decrease",
    response_model=ProductResponse
)
def decrease_product_stock(
    product_id: int,
    stock_data: StockDecrease,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("admin", "seller"))
):

    return decrease_stock(db, product_id, stock_data)

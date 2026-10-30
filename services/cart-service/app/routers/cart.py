"""Cart HTTP endpoints; mutations live in cart_operations."""

from app import cart_operations as operations
import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from app.core.config import settings
from app.core.security import get_current_user
from app.redis_client import redis_client
from app.schemas import CartItemCreate, CartItemUpdate, CartResponse
from app.storage import prepare, finish

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.post("/items", status_code=201)
def add_item_to_cart(
    item: CartItemCreate, current_user: dict = Depends(get_current_user)
):
    return operations.add_item_to_cart(item, current_user)


@router.get("", response_model=CartResponse)
def get_cart(current_user: dict = Depends(get_current_user)):
    return operations.get_cart(current_user)


@router.put("/items/{product_id}")
def update_cart_item(
    product_id: int,
    item_update: CartItemUpdate,
    current_user: dict = Depends(get_current_user),
):
    return operations.update_cart_item(product_id, item_update, current_user)


@router.delete("/items/{product_id}")
def delete_cart_item(product_id: int, current_user: dict = Depends(get_current_user)):
    return operations.delete_cart_item(product_id, current_user)


@router.delete("")
def clear_cart(current_user: dict = Depends(get_current_user)):
    return operations.clear_cart(current_user)


key_header = APIKeyHeader(name="X-Internal-Service-Key", auto_error=False)


def internal_only(key: str | None = Security(key_header)):
    if not key or not secrets.compare_digest(key, settings.INTERNAL_SERVICE_KEY):
        raise HTTPException(403, "Acceso interno no autorizado")


internal_router = APIRouter(
    prefix="/cart/internal", tags=["Checkout"], dependencies=[Depends(internal_only)]
)


@internal_router.post(
    "/{user_id}/checkout/{checkout_id}/prepare", response_model=CartResponse
)
def prepare_checkout(user_id: int, checkout_id: UUID):
    return operations.cart_response(
        user_id, prepare(redis_client, user_id, str(checkout_id))
    )


@internal_router.post("/{user_id}/checkout/{checkout_id}/commit")
def commit_checkout(user_id: int, checkout_id: UUID):
    finish(redis_client, user_id, str(checkout_id), committed=True)
    return {"checkout_id": str(checkout_id), "state": "COMMITTED"}


@internal_router.post("/{user_id}/checkout/{checkout_id}/abort")
def abort_checkout(user_id: int, checkout_id: UUID):
    finish(redis_client, user_id, str(checkout_id), committed=False)
    return {"checkout_id": str(checkout_id), "state": "ABORTED"}

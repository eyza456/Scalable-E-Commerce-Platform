from decimal import Decimal
import secrets
from uuid import UUID

import httpx
from app import http_client
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.core.security import get_current_user
from app.redis_client import redis_client
from app.schemas import CartItemCreate, CartItemUpdate, CartResponse
from app.storage import atomic, changed, prepare, finish

router = APIRouter(prefix="/cart", tags=["Cart"])


def product_snapshot(product_id):
    try:
        response = http_client.get(f"{settings.PRODUCT_SERVICE_URL}/products/{product_id}", timeout=5)
    except httpx.RequestError as exc:
        raise HTTPException(503, "Product Service no esta disponible") from exc
    if response.status_code == 404:
        raise HTTPException(404, "Producto no encontrado")
    if response.status_code != 200:
        raise HTTPException(502, "No se pudo consultar el producto")
    product = response.json()
    if not product.get("is_active"):
        raise HTTPException(409, "Producto no disponible")
    return product


def cart_response(user_id, cart):
    items = []
    total = Decimal("0.00")
    for item in cart["items"]:
        price = Decimal(item["price"])
        subtotal = price * item["quantity"]
        total += subtotal
        items.append({**item, "price": price, "subtotal": subtotal})
    return {"user_id": user_id, "items": items, "total": total,
            "version": cart["version"], "checkout_id": cart["checkout_id"],
            "last_checkout_id": cart["last_checkout_id"]}


@router.post("/items", status_code=201)
def add_item_to_cart(item: CartItemCreate, current_user: dict = Depends(get_current_user)):
    product = product_snapshot(item.product_id)
    def change(cart):
        existing = next((p for p in cart["items"] if p["product_id"] == item.product_id), None)
        quantity = (existing["quantity"] if existing else 0) + item.quantity
        if quantity > product["stock"] or quantity > 100:
            raise HTTPException(400, "Stock insuficiente o cantidad superior a 100")
        if existing is None:
            existing = {"product_id": item.product_id}
            cart["items"].append(existing)
        existing.update(name=product["name"], price=str(product["price"]), quantity=quantity)
        changed(cart)
    cart = atomic(redis_client, current_user["id"], change)
    return {"message": "Producto agregado al carrito", "cart": cart}


@router.get("", response_model=CartResponse)
def get_cart(current_user: dict = Depends(get_current_user)):
    return cart_response(current_user["id"], atomic(redis_client, current_user["id"]))


@router.put("/items/{product_id}")
def update_cart_item(product_id: int, item_update: CartItemUpdate, current_user: dict = Depends(get_current_user)):
    product = product_snapshot(product_id)
    def change(cart):
        existing = next((p for p in cart["items"] if p["product_id"] == product_id), None)
        if existing is None:
            raise HTTPException(404, "Producto no encontrado en el carrito")
        if item_update.quantity > product["stock"]:
            raise HTTPException(400, "Stock insuficiente")
        existing.update(quantity=item_update.quantity, name=product["name"], price=str(product["price"]))
        changed(cart)
    cart = atomic(redis_client, current_user["id"], change)
    return {"message": "Cantidad y precio actualizados", "cart": cart}


@router.delete("/items/{product_id}")
def delete_cart_item(product_id: int, current_user: dict = Depends(get_current_user)):
    def change(cart):
        if not any(p["product_id"] == product_id for p in cart["items"]):
            raise HTTPException(404, "Producto no encontrado en el carrito")
        cart["items"] = [p for p in cart["items"] if p["product_id"] != product_id]
        changed(cart)
    cart = atomic(redis_client, current_user["id"], change)
    return {"message": "Producto eliminado correctamente", "cart": cart}


@router.delete("")
def clear_cart(current_user: dict = Depends(get_current_user)):
    def change(cart):
        if not cart["items"]:
            raise HTTPException(404, "El carrito ya esta vacio")
        cart["items"] = []
        changed(cart)
    atomic(redis_client, current_user["id"], change)
    return {"message": "Carrito vaciado correctamente"}


key_header = APIKeyHeader(name="X-Internal-Service-Key", auto_error=False)


def internal_only(key: str | None = Security(key_header)):
    if not key or not secrets.compare_digest(key, settings.INTERNAL_SERVICE_KEY):
        raise HTTPException(403, "Acceso interno no autorizado")


internal_router = APIRouter(prefix="/cart/internal", tags=["Checkout"], dependencies=[Depends(internal_only)])


@internal_router.post("/{user_id}/checkout/{checkout_id}/prepare", response_model=CartResponse)
def prepare_checkout(user_id: int, checkout_id: UUID):
    return cart_response(user_id, prepare(redis_client, user_id, str(checkout_id)))


@internal_router.post("/{user_id}/checkout/{checkout_id}/commit")
def commit_checkout(user_id: int, checkout_id: UUID):
    finish(redis_client, user_id, str(checkout_id), committed=True)
    return {"checkout_id": str(checkout_id), "state": "COMMITTED"}


@internal_router.post("/{user_id}/checkout/{checkout_id}/abort")
def abort_checkout(user_id: int, checkout_id: UUID):
    finish(redis_client, user_id, str(checkout_id), committed=False)
    return {"checkout_id": str(checkout_id), "state": "ABORTED"}

"""Cart use cases and atomic storage coordination."""

from decimal import Decimal
import httpx
from app import http_client
from fastapi import HTTPException
from app.core.config import settings
from app.redis_client import redis_client
from app.schemas import CartItemCreate, CartItemUpdate
from app.storage import atomic, changed


def product_snapshot(product_id):
    try:
        response = http_client.get(
            f"{settings.PRODUCT_SERVICE_URL}/products/{product_id}", timeout=5
        )
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
    return {
        "user_id": user_id,
        "items": items,
        "total": total,
        "version": cart["version"],
        "checkout_id": cart["checkout_id"],
        "last_checkout_id": cart["last_checkout_id"],
    }


def add_item_to_cart(item: CartItemCreate, current_user: dict):
    product = product_snapshot(item.product_id)

    def change(cart):
        existing = next(
            (p for p in cart["items"] if p["product_id"] == item.product_id), None
        )
        quantity = (existing["quantity"] if existing else 0) + item.quantity
        if quantity > product["stock"] or quantity > 100:
            raise HTTPException(400, "Stock insuficiente o cantidad superior a 100")
        if existing is None:
            existing = {"product_id": item.product_id}
            cart["items"].append(existing)
        existing.update(
            name=product["name"], price=str(product["price"]), quantity=quantity
        )
        changed(cart)

    cart = atomic(redis_client, current_user["id"], change)
    return {"message": "Producto agregado al carrito", "cart": cart}


def get_cart(current_user: dict):
    return cart_response(current_user["id"], atomic(redis_client, current_user["id"]))


def update_cart_item(product_id: int, item_update: CartItemUpdate, current_user: dict):
    product = product_snapshot(product_id)

    def change(cart):
        existing = next(
            (p for p in cart["items"] if p["product_id"] == product_id), None
        )
        if existing is None:
            raise HTTPException(404, "Producto no encontrado en el carrito")
        if item_update.quantity > product["stock"]:
            raise HTTPException(400, "Stock insuficiente")
        existing.update(
            quantity=item_update.quantity,
            name=product["name"],
            price=str(product["price"]),
        )
        changed(cart)

    cart = atomic(redis_client, current_user["id"], change)
    return {"message": "Cantidad y precio actualizados", "cart": cart}


def delete_cart_item(product_id: int, current_user: dict):

    def change(cart):
        if not any((p["product_id"] == product_id for p in cart["items"])):
            raise HTTPException(404, "Producto no encontrado en el carrito")
        cart["items"] = [p for p in cart["items"] if p["product_id"] != product_id]
        changed(cart)

    cart = atomic(redis_client, current_user["id"], change)
    return {"message": "Producto eliminado correctamente", "cart": cart}


def clear_cart(current_user: dict):

    def change(cart):
        if not cart["items"]:
            raise HTTPException(404, "El carrito ya esta vacio")
        cart["items"] = []
        changed(cart)

    atomic(redis_client, current_user["id"], change)
    return {"message": "Carrito vaciado correctamente"}

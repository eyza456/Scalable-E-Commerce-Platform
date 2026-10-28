import json
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import get_current_user
from app.redis_client import redis_client
from app.schemas import (
    CartItemCreate,
    CartItemResponse,
    CartItemUpdate,
    CartResponse
)

router = APIRouter(
    prefix="/cart",
    tags=["Cart"]
)


@router.post(
    "/items",
    status_code=status.HTTP_201_CREATED
)
def add_item_to_cart(
    item: CartItemCreate,
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user["id"]

    # =========================
    # CONSULTAR PRODUCT SERVICE
    # =========================

    try:

        response = httpx.get(
            f"{settings.PRODUCT_SERVICE_URL}/products/{item.product_id}",
            timeout=5.0
        )

    except httpx.RequestError:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product Service no está disponible"
        )

    # =========================
    # PRODUCTO NO EXISTE
    # =========================

    if response.status_code == 404:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )

    # =========================
    # ERROR PRODUCT SERVICE
    # =========================

    if response.status_code != 200:

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al consultar Product Service"
        )

    product = response.json()

    # =========================
    # COMPROBAR STOCK
    # =========================

    if product["stock"] < item.quantity:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stock insuficiente"
        )

    # =========================
    # CLAVE REDIS
    # =========================

    cart_key = f"cart:{user_id}"

    # =========================
    # OBTENER CARRITO ACTUAL
    # =========================

    cart_data = redis_client.get(cart_key)

    if cart_data:

        cart = json.loads(cart_data)

    else:

        cart = {
            "items": []
        }

    # =========================
    # BUSCAR PRODUCTO
    # =========================

    existing_item = None

    for cart_item in cart["items"]:

        if cart_item["product_id"] == item.product_id:

            existing_item = cart_item
            break

    # =========================
    # AGREGAR / ACTUALIZAR
    # =========================

    if existing_item:

        new_quantity = (
            existing_item["quantity"]
            + item.quantity
        )

        if new_quantity > product["stock"]:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La cantidad solicitada supera el stock disponible"
            )

        existing_item["quantity"] = new_quantity

    else:

        cart["items"].append({

            "product_id": item.product_id,

            "name": product["name"],

            "price": str(product["price"]),

            "quantity": item.quantity

        })

    # =========================
    # GUARDAR EN REDIS
    # =========================

    redis_client.set(
        cart_key,
        json.dumps(cart)
    )

    return {
        "message": "Producto agregado al carrito",
        "cart": cart
    }

@router.get(
    "",
    response_model=CartResponse
)
def get_cart(
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user["id"]

    cart_key = f"cart:{user_id}"

    # =========================
    # OBTENER CARRITO DE REDIS
    # =========================

    cart_data = redis_client.get(cart_key)

    # =========================
    # CARRITO VACÍO
    # =========================

    if not cart_data:

        return {
            "user_id": user_id,
            "items": [],
            "total": Decimal("0.00")
        }

    cart = json.loads(cart_data)

    items = []

    total = Decimal("0.00")

    # =========================
    # CALCULAR SUBTOTALES
    # =========================

    for item in cart["items"]:

        price = Decimal(item["price"])

        quantity = item["quantity"]

        subtotal = price * quantity

        total += subtotal

        items.append({
            "product_id": item["product_id"],
            "name": item["name"],
            "quantity": quantity,
            "price": price,
            "subtotal": subtotal
        })

    return {
        "user_id": user_id,
        "items": items,
        "total": total
    }
@router.put(
    "/items/{product_id}"
)
def update_cart_item(
    product_id: int,
    item_update: CartItemUpdate,
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user["id"]

    cart_key = f"cart:{user_id}"

    # =========================
    # OBTENER CARRITO
    # =========================

    cart_data = redis_client.get(cart_key)

    if not cart_data:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El carrito está vacío"
        )

    cart = json.loads(cart_data)

    # =========================
    # BUSCAR PRODUCTO
    # =========================

    existing_item = None

    for cart_item in cart["items"]:

        if cart_item["product_id"] == product_id:

            existing_item = cart_item
            break

    if not existing_item:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado en el carrito"
        )

    # =========================
    # CONSULTAR PRODUCT SERVICE
    # =========================

    try:

        response = httpx.get(
            f"{settings.PRODUCT_SERVICE_URL}/products/{product_id}",
            timeout=5.0
        )

    except httpx.RequestError:

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Product Service no está disponible"
        )

    if response.status_code == 404:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El producto ya no existe"
        )

    if response.status_code != 200:

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al consultar Product Service"
        )

    product = response.json()

    # =========================
    # VALIDAR STOCK
    # =========================

    if item_update.quantity > product["stock"]:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cantidad solicitada supera el stock disponible"
        )

    # =========================
    # ACTUALIZAR CANTIDAD
    # =========================

    existing_item["quantity"] = item_update.quantity

    # =========================
    # GUARDAR EN REDIS
    # =========================

    redis_client.set(
        cart_key,
        json.dumps(cart)
    )

    return {
        "message": "Cantidad actualizada correctamente",
        "cart": cart
    }

@router.delete(
    "/items/{product_id}"
)
def delete_cart_item(
    product_id: int,
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user["id"]

    cart_key = f"cart:{user_id}"

    # =========================
    # OBTENER CARRITO
    # =========================

    cart_data = redis_client.get(cart_key)

    if not cart_data:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El carrito está vacío"
        )

    cart = json.loads(cart_data)

    # =========================
    # BUSCAR PRODUCTO
    # =========================

    item_found = False

    for item in cart["items"]:

        if item["product_id"] == product_id:

            cart["items"].remove(item)

            item_found = True

            break

    # =========================
    # PRODUCTO NO ENCONTRADO
    # =========================

    if not item_found:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado en el carrito"
        )

    # =========================
    # CARRITO QUEDÓ VACÍO
    # =========================

    if not cart["items"]:

        redis_client.delete(cart_key)

        return {
            "message": "Producto eliminado. El carrito está vacío"
        }

    # =========================
    # ACTUALIZAR REDIS
    # =========================

    redis_client.set(
        cart_key,
        json.dumps(cart)
    )

    return {
        "message": "Producto eliminado correctamente",
        "cart": cart
    }

@router.delete("")
def clear_cart(
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user["id"]

    cart_key = f"cart:{user_id}"

    # =========================
    # COMPROBAR SI EXISTE
    # =========================

    cart_exists = redis_client.exists(cart_key)

    if not cart_exists:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El carrito ya está vacío"
        )

    # =========================
    # ELIMINAR CARRITO
    # =========================

    redis_client.delete(cart_key)

    return {
        "message": "Carrito vaciado correctamente"
    }
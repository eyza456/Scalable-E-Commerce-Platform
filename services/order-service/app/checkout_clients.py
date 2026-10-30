"""HTTP adapters for checkout contracts; no SQL, Redis or order decisions."""

import httpx
from decimal import Decimal
from pydantic import BaseModel, Field, StrictBool
from app import http_client
from app.core.config import settings


class ProductContract(BaseModel):
    id: int = Field(strict=True, gt=0)
    name: str = Field(min_length=1)
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    stock: int = Field(strict=True, ge=0)
    is_active: StrictBool


class CartReadError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        super().__init__(message)


def get_cart(token):
    try:
        response = http_client.get(
            f"{settings.CART_SERVICE_URL}/cart",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if response.status_code != 200:
            raise CartReadError(response.status_code, "No se pudo consultar el carrito")
        cart = response.json()
        if not isinstance(cart, dict) or not isinstance(cart.get("items"), list):
            raise ValueError("Contrato de carrito incompatible")
        return cart
    except (httpx.RequestError, ValueError) as exc:
        raise CartReadError(503, "Carrito no disponible") from exc


def get_product(product_id):
    try:
        response = http_client.get(
            f"{settings.PRODUCT_SERVICE_URL}/products/{product_id}", timeout=5
        )
        if response.status_code == 404:
            raise Rejected("PRODUCT_UNAVAILABLE", "Un producto ya no existe")
        if response.status_code != 200:
            raise Unavailable("No se pudo consultar el catalogo")
        product = ProductContract.model_validate(response.json())
        if product.id != product_id:
            raise ValueError("Producto de otro identificador")
        return product.model_dump()
    except (httpx.RequestError, ValueError) as exc:
        raise Unavailable("Catalogo temporalmente no disponible") from exc


class Unavailable(Exception):
    pass


class Rejected(Exception):

    def __init__(self, code, message):
        self.code, self.message = (code, message)


def cart_call(checkout, action):
    try:
        response = http_client.post(
            settings.CART_SERVICE_URL.rstrip("/")
            + f"/cart/internal/{checkout.user_id}/checkout/{checkout.id}/{action}",
            headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY},
            timeout=5,
        )
        data = response.json()
    except (httpx.RequestError, ValueError) as exc:
        raise Unavailable("Carrito temporalmente no disponible") from exc
    if action == "prepare" and response.status_code == 409:
        raise Rejected("STALE_CART", "El carrito cambio; actualizar antes de confirmar")
    if response.status_code != 200 or not isinstance(data, dict):
        raise Unavailable("No se pudo coordinar el carrito")
    if action != "prepare":
        expected = "COMMITTED" if action == "commit" else "ABORTED"
        if data.get("checkout_id") != checkout.id or data.get("state") != expected:
            raise Unavailable("Confirmacion de carrito invalida")
    return data

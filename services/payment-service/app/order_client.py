"""Consumer-owned Order API contracts. No SQL or payment decisions."""

from decimal import Decimal
from typing import Literal
import httpx
from pydantic import BaseModel, Field, model_validator
from app import http_client
from app.core.config import settings

OrderStatus = Literal[
    "PENDING", "CANCELLING", "CANCELLED", "PAID", "PROCESSING", "SHIPPED", "DELIVERED"
]


class OrderReadError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        super().__init__(message)


class OrderItemContract(BaseModel):
    product_id: int = Field(strict=True, gt=0)
    quantity: int = Field(strict=True, ge=1, le=100)


class OwnedOrderContract(BaseModel):
    id: int = Field(strict=True, gt=0)
    user_id: int = Field(strict=True, gt=0)
    status: OrderStatus
    total: Decimal = Field(gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False)
    items: list[OrderItemContract] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_products(self):
        if len({i.product_id for i in self.items}) != len(self.items):
            raise ValueError("Repeated product in order snapshot")
        return self


class InternalOrderContract(BaseModel):
    order_id: int = Field(strict=True, gt=0)
    user_id: int = Field(strict=True, gt=0)
    status: OrderStatus


def get_owned_order(order_id, token):
    try:
        response = http_client.get(
            settings.ORDER_SERVICE_URL.rstrip("/") + f"/orders/{order_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.RequestError as exc:
        raise OrderReadError(503, "No se pudo conectar con Order Service") from exc
    if response.status_code == 404:
        raise OrderReadError(404, "La orden no existe")
    if response.status_code != 200:
        code = response.status_code if 400 <= response.status_code <= 599 else 503
        raise OrderReadError(code, "No se pudo obtener la orden")
    try:
        order = OwnedOrderContract.model_validate(response.json())
        if order.id != order_id:
            raise ValueError("Order ID mismatch")
        return order.model_dump()
    except (ValueError, TypeError) as exc:
        raise OrderReadError(503, "Respuesta de Order Service no verificable") from exc


def get_internal_order(order_id):
    try:
        response = http_client.get(
            settings.ORDER_SERVICE_URL.rstrip("/") + f"/orders/internal/{order_id}",
            headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY},
            timeout=10,
        )
        if response.status_code != 200:
            raise OrderReadError(503, "No se pudo verificar la orden")
        order = InternalOrderContract.model_validate(response.json())
        if order.order_id != order_id:
            raise ValueError("Order ID mismatch")
        return order.model_dump()
    except (httpx.RequestError, ValueError, TypeError) as exc:
        raise OrderReadError(503, "No se pudo verificar la orden") from exc

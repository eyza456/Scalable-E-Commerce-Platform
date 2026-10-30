"""Inventory HTTP protocol; no database access or state transitions."""

from urllib.parse import quote
import httpx
from app import http_client
from app.core.config import settings


def release_order_stock(order_id):
    try:
        response = http_client.post(
            settings.PRODUCT_SERVICE_URL.rstrip("/")
            + f"/inventory/internal/orders/{order_id}/release",
            headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY},
            timeout=10,
        )
        data = response.json()
        if (
            response.status_code != 200
            or not isinstance(data, dict)
            or type(data.get("order_id")) is not int
            or data["order_id"] != order_id
            or data.get("status") != "RELEASED"
        ):
            raise InventoryUnavailable("Liberacion no confirmada")
    except (httpx.RequestError, ValueError) as exc:
        raise InventoryUnavailable("Inventario no disponible") from exc


class StockUnavailable(Exception):
    pass


class InventoryUnavailable(Exception):
    pass


def reserve_stock(transaction_id):
    try:
        response = http_client.post(
            settings.PRODUCT_SERVICE_URL.rstrip("/")
            + "/inventory/internal/reservations/"
            + quote(transaction_id, safe=""),
            headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY},
            timeout=10,
        )
        data = response.json()
    except (httpx.RequestError, ValueError) as exc:
        raise InventoryUnavailable("Inventario no disponible; se reintentara") from exc
    detail = data.get("detail") if isinstance(data, dict) else None
    if (
        response.status_code == 409
        and isinstance(detail, dict)
        and (detail.get("code") == "INSUFFICIENT_STOCK")
    ):
        raise StockUnavailable(detail.get("message", "Stock insuficiente"))
    if (
        response.status_code != 200
        or not isinstance(data, dict)
        or data.get("reservation_id") != transaction_id
        or (data.get("status") not in ("RESERVED", "CONSUMED"))
    ):
        raise InventoryUnavailable("No se pudo confirmar la reserva; se reintentara")

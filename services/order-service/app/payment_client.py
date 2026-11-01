"""Adaptador del contrato interno de Payment Service para cancelaciones."""

import httpx
from pydantic import ValidationError

from app import http_client
from app.cancellation_contracts import CancellationDone, PaymentConfirmedDetail
from app.core.config import settings


def request_cancellation(order_id: int, user_id: int) -> str | None:
    """Devuelve CANCELLED/PAID o None si la cancelacion debe recuperarse."""
    try:
        response = http_client.post(
            settings.PAYMENT_SERVICE_URL.rstrip("/")
            + f"/payments/internal/orders/{order_id}/cancel",
            headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY},
            timeout=5,
        )
        data = response.json()
        if response.status_code == 200:
            result = CancellationDone.model_validate(data)
            if result.order_id != order_id or result.user_id != user_id:
                return None
            return "CANCELLED"
        if response.status_code == 409 and isinstance(data, dict):
            detail = data.get("detail")
            result = PaymentConfirmedDetail.model_validate(detail)
            if result.order_id == order_id:
                return "PAID"
        return None
    except (httpx.RequestError, ValueError, ValidationError, TypeError):
        return None

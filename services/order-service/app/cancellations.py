import logging
import httpx
from app import http_client

from app.core.config import settings
from app.database import SessionLocal
from app.models import Order

logger = logging.getLogger(__name__)


def finish_cancellation(db, order_id):
    order = db.get(Order, order_id)
    if order is None or order.status != "CANCELLING":
        return order
    user_id = order.user_id
    db.rollback()
    outcome = None
    try:
        response = http_client.post(
            settings.PAYMENT_SERVICE_URL.rstrip("/") + f"/payments/internal/orders/{order_id}/cancel",
            headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY}, timeout=5,
        )
        data = response.json()
        if (response.status_code == 200 and isinstance(data, dict)
                and data.get("order_id") == order_id and data.get("user_id") == user_id
                and data.get("status") == "DONE"):
            outcome = "CANCELLED"
        elif (response.status_code == 409 and isinstance(data, dict)
              and isinstance(data.get("detail"), dict)
              and data["detail"].get("code") == "PAYMENT_CONFIRMED"
              and data["detail"].get("order_id") == order_id):
            # Payment es autoritativo: no depender de un evento atrasado.
            outcome = "PAID"
        else:
            logger.warning("Cancelacion de orden %s pendiente: HTTP %s", order_id, response.status_code)
    except (httpx.RequestError, ValueError):
        logger.warning("Cancelacion de orden %s pendiente de recuperacion", order_id)
    order = db.query(Order).filter_by(id=order_id).with_for_update().populate_existing().first()
    if order is not None and order.status == "CANCELLING" and outcome is not None:
        order.status = outcome
    db.commit()
    return order


def recover_cancellations():
    with SessionLocal() as db:
        ids = [row[0] for row in db.query(Order.id).filter_by(status="CANCELLING").all()]
    for order_id in ids:
        try:
            with SessionLocal() as db:
                finish_cancellation(db, order_id)
        except Exception:
            logger.exception("No se pudo recuperar la cancelacion %s", order_id)


def run_recovery(stop):
    while not stop.is_set():
        try:
            recover_cancellations()
        except Exception:
            logger.exception("Recuperador de cancelaciones no disponible")
        stop.wait(5)

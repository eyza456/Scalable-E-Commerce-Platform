import logging
from datetime import datetime, timezone

import httpx
from app import http_client
from fastapi import HTTPException
from sqlalchemy import text

from app.core.config import settings
from app.database import SessionLocal
from app.models import Payment, OrderCancellation

logger = logging.getLogger(__name__)


def begin_cancellation(db, order_id, user_id):
    # Mismo bloqueo que crear/confirmar pagos: solo puede ganar uno de los flujos.
    db.execute(text("SELECT pg_advisory_xact_lock(17001, :id)"), {"id": order_id})
    if db.query(Payment.id).filter_by(order_id=order_id, status="PAID").first():
        raise HTTPException(409, {"code": "PAYMENT_CONFIRMED", "order_id": order_id})
    cancellation = db.get(OrderCancellation, order_id)
    if cancellation is None:
        cancellation = OrderCancellation(order_id=order_id, user_id=user_id)
        db.add(cancellation)
    elif cancellation.user_id != user_id:
        raise HTTPException(409, "El propietario no coincide")
    db.query(Payment).filter_by(order_id=order_id, status="PENDING").update(
        {"status": "CANCELLED", "processed_at": datetime.now(timezone.utc)}, synchronize_session=False)
    db.commit()
    return cancellation


def finish_cancellation(db, order_id, skip_locked=False):
    cancellation = (db.query(OrderCancellation).filter_by(order_id=order_id)
                    .with_for_update(skip_locked=skip_locked).populate_existing().first())
    if cancellation is None:
        db.rollback()
        return None
    if cancellation.status != "DONE":
        try:
            response = http_client.post(
                settings.PRODUCT_SERVICE_URL.rstrip("/") + f"/inventory/internal/orders/{order_id}/release",
                headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY}, timeout=10,
            )
            data = response.json()
            if (response.status_code == 200 and isinstance(data, dict)
                    and data.get("order_id") == order_id and data.get("status") == "RELEASED"):
                cancellation.status = "DONE"
            else:
                logger.warning("Liberacion de orden %s pendiente: HTTP %s", order_id, response.status_code)
        except (httpx.RequestError, ValueError):
            logger.warning("Liberacion de orden %s pendiente; inventario no disponible", order_id)
    db.commit()
    return cancellation


def recover_cancellations():
    with SessionLocal() as db:
        ids = [row[0] for row in db.query(OrderCancellation.order_id).filter_by(status="PENDING").all()]
    for order_id in ids:
        try:
            with SessionLocal() as db:
                finish_cancellation(db, order_id, skip_locked=True)
        except Exception:
            logger.exception("No se pudo recuperar la cancelacion de la orden %s", order_id)

"""Confirmacion recuperable de pagos simulados tras reservar inventario."""
import logging
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.rabbitmq import PAYMENT_QUEUES
from app.database import SessionLocal
from app.models import Payment, OutboxEvent, OrderCancellation
from sqlalchemy import text

logger = logging.getLogger(__name__)


class StockUnavailable(Exception):
    pass


class InventoryUnavailable(Exception):
    pass


def reserve_stock(payment):
    try:
        response = httpx.post(
            settings.PRODUCT_SERVICE_URL.rstrip("/") + "/inventory/internal/reservations/"
            + quote(payment.transaction_id, safe=""),
            headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY},
            timeout=10,
        )
        data = response.json()
    except (httpx.RequestError, ValueError) as exc:
        raise InventoryUnavailable("Inventario no disponible; se reintentara") from exc
    detail = data.get("detail") if isinstance(data, dict) else None
    if response.status_code == 409 and isinstance(detail, dict) and detail.get("code") == "INSUFFICIENT_STOCK":
        raise StockUnavailable(detail.get("message", "Stock insuficiente"))
    if (response.status_code != 200 or not isinstance(data, dict)
            or data.get("reservation_id") != payment.transaction_id
            or data.get("status") not in ("RESERVED", "CONSUMED")):
        # Un conflicto o una respuesta ambigua no autoriza confirmar ni rechazar.
        raise InventoryUnavailable("No se pudo confirmar la reserva; se reintentara")


def settle_payment(db, payment_id, skip_locked=False):
    """El bloqueo evita que HTTP y el recuperador confirmen dos veces un intento.

    El intento ya esta confirmado en DB antes de llamar a Product. Si cae el
    proceso tras reservar, la siguiente ejecucion reutiliza la misma reserva.
    """
    order_id = db.query(Payment.order_id).filter_by(id=payment_id).scalar()
    if order_id is None:
        db.rollback()
        return None
    if skip_locked:
        locked = db.execute(text("SELECT pg_try_advisory_xact_lock(17001, :id)"), {"id": order_id}).scalar()
        if not locked:
            db.rollback()
            return None
    else:
        db.execute(text("SELECT pg_advisory_xact_lock(17001, :id)"), {"id": order_id})
    payment = (
        db.query(Payment).filter_by(id=payment_id)
        .with_for_update(skip_locked=skip_locked).populate_existing().first()
    )
    if payment is None:
        db.rollback()
        return None
    if payment.status != "PENDING" or payment.event_payload is None:
        db.commit()
        return payment
    if db.get(OrderCancellation, order_id):
        payment.status = "CANCELLED"
        payment.processed_at = datetime.now(timezone.utc)
        db.commit()
        return payment
    try:
        reserve_stock(payment)
    except StockUnavailable:
        # Product garantiza rollback de todos los items si falta uno.
        payment.status = "REJECTED"
    except InventoryUnavailable as exc:
        logger.warning("Pago %s pendiente de reserva: %s", payment.transaction_id, exc)
        db.commit()
        return payment
    else:
        payment.status = "PAID"
        for destination in PAYMENT_QUEUES:
            db.add(OutboxEvent(
                event_type="PAYMENT_COMPLETED", aggregate_id=payment.order_id,
                destination=destination, payload=payment.event_payload,
            ))
    payment.processed_at = datetime.now(timezone.utc)
    try:
        # PAID y todas sus entregas son atomicos. PENDING permanece durable
        # si este commit falla; no se libera stock ante una respuesta incierta.
        db.commit()
    except Exception:
        db.rollback()
        raise
    return payment


def recover_pending():
    with SessionLocal() as db:
        ids = [row[0] for row in db.query(Payment.id).filter(
            Payment.status == "PENDING", Payment.event_payload.is_not(None),
        ).order_by(Payment.id).all()]
    for payment_id in ids:
        try:
            with SessionLocal() as db:
                settle_payment(db, payment_id, skip_locked=True)
        except Exception:
            logger.exception("No se pudo recuperar el pago %s", payment_id)


def run_recovery(stop):
    while not stop.is_set():
        try:
            from app.cancellations import recover_cancellations
            recover_cancellations()
            recover_pending()
        except Exception:
            logger.exception("Recuperacion de pagos temporalmente no disponible")
        stop.wait(5)

"""Confirmacion recuperable de pagos simulados tras reservar inventario."""

import logging
from datetime import datetime, timezone


from app.core.rabbitmq import PAYMENT_QUEUES
from app.database import SessionLocal
from app.models import OutboxEvent
from app import payment_repository as repository, inventory_client
from app.inventory_client import StockUnavailable, InventoryUnavailable

logger = logging.getLogger(__name__)

SIMULATED_REJECTIONS = {
    "insufficient_funds": "INSUFFICIENT_FUNDS",
    "expired_card": "EXPIRED_CARD",
    "card_declined": "CARD_DECLINED",
}
REJECTION_MESSAGES = {
    "INSUFFICIENT_STOCK": "Pago rechazado sin cobro: stock insuficiente",
    "INSUFFICIENT_FUNDS": "Pago simulado rechazado: fondos insuficientes",
    "EXPIRED_CARD": "Pago simulado rechazado: tarjeta vencida",
    "CARD_DECLINED": "Pago simulado rechazado por el emisor",
}


def reserve_stock(payment):
    return inventory_client.reserve_stock(payment.transaction_id)


def settle_payment(db, payment_id, skip_locked=False):
    """El bloqueo evita que HTTP y el recuperador confirmen dos veces un intento.

    El intento ya esta confirmado en DB antes de llamar a Product. Si cae el
    proceso tras reservar, la siguiente ejecucion reutiliza la misma reserva.
    """
    order_id = repository.order_for_payment(db, payment_id)
    if order_id is None:
        db.rollback()
        return None
    if not repository.lock_order(db, order_id, skip=skip_locked):
        db.rollback()
        return None
    payment = repository.locked_payment(db, payment_id, skip=skip_locked)
    if payment is None:
        db.rollback()
        return None
    if payment.status != "PENDING" or payment.event_payload is None:
        db.commit()
        return payment
    if repository.cancellation(db, order_id):
        payment.status = "CANCELLED"
        payment.processed_at = datetime.now(timezone.utc)
        db.commit()
        return payment
    # Resultado persistido al crear el intento. El recuperador usa la misma
    # decision y nunca reserva stock para un rechazo de autorizacion.
    rejection = SIMULATED_REJECTIONS.get(payment.simulation_result)
    if rejection:
        payment.status = "REJECTED"
        payment.rejection_code = rejection
        payment.processed_at = datetime.now(timezone.utc)
        db.commit()
        return payment
    try:
        reserve_stock(payment)
    except StockUnavailable:
        # Product garantiza rollback de todos los items si falta uno.
        payment.status = "REJECTED"
        payment.rejection_code = "INSUFFICIENT_STOCK"
    except InventoryUnavailable as exc:
        logger.warning("Pago %s pendiente de reserva: %s", payment.transaction_id, exc)
        db.commit()
        return payment
    else:
        payment.status = "PAID"
        for destination in PAYMENT_QUEUES:
            db.add(
                OutboxEvent(
                    event_type="PAYMENT_COMPLETED",
                    aggregate_id=payment.order_id,
                    destination=destination,
                    payload=payment.event_payload,
                )
            )
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
        ids = repository.pending_payment_ids(db)
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

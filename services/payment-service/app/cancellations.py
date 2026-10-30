import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import OrderCancellation
from app import payment_repository as repository, inventory_client
from app.inventory_client import InventoryUnavailable

logger = logging.getLogger(__name__)


def begin_cancellation(db, order_id, user_id):
    # Mismo bloqueo que crear/confirmar pagos: solo puede ganar uno de los flujos.
    repository.lock_order(db, order_id)
    if repository.has_paid(db, order_id):
        raise HTTPException(409, {"code": "PAYMENT_CONFIRMED", "order_id": order_id})
    cancellation = repository.cancellation(db, order_id)
    if cancellation is None:
        cancellation = OrderCancellation(order_id=order_id, user_id=user_id)
        db.add(cancellation)
    elif cancellation.user_id != user_id:
        raise HTTPException(409, "El propietario no coincide")
    repository.cancel_pending(db, order_id, datetime.now(timezone.utc))
    db.commit()
    return cancellation


def finish_cancellation(db, order_id, skip_locked=False):
    cancellation = repository.locked_cancellation(db, order_id, skip=skip_locked)
    if cancellation is None:
        db.rollback()
        return None
    if cancellation.status != "DONE":
        try:
            inventory_client.release_order_stock(order_id)
            cancellation.status = "DONE"
        except InventoryUnavailable:
            logger.warning(
                "Liberacion de orden %s pendiente; inventario no verificable", order_id
            )
    db.commit()
    return cancellation


def recover_cancellations():
    with SessionLocal() as db:
        ids = repository.pending_cancellation_ids(db)
    for order_id in ids:
        try:
            with SessionLocal() as db:
                finish_cancellation(db, order_id, skip_locked=True)
        except Exception:
            logger.exception(
                "No se pudo recuperar la cancelacion de la orden %s", order_id
            )

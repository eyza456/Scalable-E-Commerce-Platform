import logging
from app import http_client

from app.database import SessionLocal
from app.models import Order
from app.payment_client import request_cancellation

logger = logging.getLogger(__name__)


def finish_cancellation(db, order_id):
    order = db.get(Order, order_id)
    if order is None or order.status != "CANCELLING":
        return order
    user_id = order.user_id
    db.rollback()
    outcome = request_cancellation(order_id, user_id)
    if outcome is None:
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

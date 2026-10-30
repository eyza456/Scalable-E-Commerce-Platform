"""Payment use cases; transaction commits stay in the application layer."""

import uuid
from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session
from app.inventory import settle_payment, REJECTION_MESSAGES
from app.models import Payment
from app.cancellations import begin_cancellation, finish_cancellation
from app.schemas import PaymentCreate
from app import payment_repository as repository
from app.order_client import get_owned_order, get_internal_order, OrderReadError


def create_payment(
    payment_data: PaymentCreate, current_user: dict, db: Session, response: Response
):
    user_id = current_user["id"]
    token = current_user["token"]
    try:
        order = get_owned_order(payment_data.order_id, token)
    except OrderReadError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if order["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para pagar esta orden",
        )
    if order["status"] != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La orden no está pendiente de pago",
        )
    repository.lock_order(db, payment_data.order_id)
    if repository.cancellation(db, payment_data.order_id):
        raise HTTPException(409, "La orden fue cancelada o esta en cancelacion")
    existing_payment = repository.active_payment(db, payment_data.order_id)
    if existing_payment and existing_payment.status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La orden ya fue pagada"
        )
    if existing_payment and existing_payment.event_payload is None:
        raise HTTPException(
            409,
            "El intento historico no tiene snapshot de inventario; requiere revision",
        )
    if (
        existing_payment
        and existing_payment.simulation_result != payment_data.simulation_result
    ):
        raise HTTPException(
            409, "El resultado simulado del intento pendiente no puede cambiar"
        )
    transaction_id = f"TX-{uuid.uuid4().hex[:12].upper()}"
    payment = Payment(
        order_id=order["id"],
        user_id=user_id,
        amount=order["total"],
        method=payment_data.method,
        simulation_result=payment_data.simulation_result,
        status="PENDING",
        transaction_id=transaction_id,
    )
    event = {
        "event": "PAYMENT_COMPLETED",
        "order_id": order["id"],
        "user_id": user_id,
        "email": current_user["email"],
        "amount": str(payment.amount),
        "transaction_id": transaction_id,
        "inventory_reservation_id": transaction_id,
        "items": [
            {"product_id": item["product_id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    }
    if existing_payment:
        payment = existing_payment
    else:
        payment.event_payload = event
        db.add(payment)
    try:
        db.commit()
        payment_id = payment.id
        db.rollback()
        payment = settle_payment(db, payment_id)
    except Exception:
        db.rollback()
        raise
    if payment.status == "REJECTED":
        code = payment.rejection_code or "INSUFFICIENT_STOCK"
        raise HTTPException(
            409,
            detail={
                "code": code,
                "transaction_id": payment.transaction_id,
                "message": REJECTION_MESSAGES[code],
            },
        )
    if payment.status == "CANCELLED":
        raise HTTPException(409, "El pago fue cancelado junto con la orden")
    if payment.status == "PENDING" and response is not None:
        response.status_code = status.HTTP_202_ACCEPTED
    return payment


def get_order_cancellation(order_id: int, db: Session):
    cancellation = repository.cancellation(db, order_id)
    if cancellation is None:
        raise HTTPException(404, "Cancelacion no encontrada")
    return {
        "order_id": order_id,
        "user_id": cancellation.user_id,
        "status": cancellation.status,
    }


def cancel_order_payments(order_id: int, response: Response, db: Session):
    try:
        order = get_internal_order(order_id)
    except OrderReadError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    if order.get("order_id") != order_id or order.get("status") not in (
        "CANCELLING",
        "CANCELLED",
    ):
        raise HTTPException(409, "La orden no tiene una cancelacion solicitada")
    begin_cancellation(db, order_id, order["user_id"])
    cancellation = finish_cancellation(db, order_id)
    if cancellation.status != "DONE":
        response.status_code = 202
    return {
        "order_id": order_id,
        "user_id": cancellation.user_id,
        "status": cancellation.status,
    }


def get_latest_order_payment(order_id: int, current_user: dict, db: Session):
    payment = repository.latest_owned(db, order_id, current_user["id"])
    if payment is None:
        raise HTTPException(404, "No hay intentos de pago para este pedido")
    return payment


def get_payment_by_transaction(transaction_id: str, current_user: dict, db: Session):
    payment = repository.by_transaction(db, transaction_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaccion no encontrada"
        )
    if payment.user_id != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para consultar esta transaccion",
        )
    return {
        "transaction_id": payment.transaction_id,
        "order_id": payment.order_id,
        "status": payment.status,
        "amount": float(payment.amount),
        "processed_at": payment.processed_at,
        "rejection_code": payment.rejection_code,
        "method": payment.method,
    }


def get_internal_payment_transaction(transaction_id: str, db: Session):
    payment = repository.by_transaction(db, transaction_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaccion no encontrada"
        )
    return {
        "transaction_id": payment.transaction_id,
        "order_id": payment.order_id,
        "user_id": payment.user_id,
        "status": payment.status,
        "processed_at": payment.processed_at,
        "rejection_code": payment.rejection_code,
        "items": (payment.event_payload or {}).get("items"),
        "inventory_reservation_id": (payment.event_payload or {}).get(
            "inventory_reservation_id"
        ),
        "amount": str(payment.amount),
    }

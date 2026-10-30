"""Order use cases. Transactions remain owned by the application layer."""

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Literal
from uuid import UUID
from app.cancellations import finish_cancellation
from app.checkouts import begin_checkout, process_checkout
from app.schemas.order import CheckoutPendingResponse
from app.schemas import OrderResponse, OrderStatusUpdate
from app import order_repository as repository


def checkout_result(db, checkout_id, user_id, response, created=False):
    checkout = repository.checkout(db, checkout_id)
    if checkout is None or checkout.user_id != user_id:
        raise HTTPException(404, "Checkout no encontrado")
    if checkout.order_id is not None:
        response.status_code = 201 if created else 200
        response.headers["X-Checkout-Status"] = checkout.state
        return repository.get(db, checkout.order_id, eager=True)
    if checkout.state in ("ABORTING", "REJECTED"):
        raise HTTPException(
            409,
            {
                "code": checkout.error_code,
                "message": checkout.error_message,
                "checkout_id": checkout.id,
            },
        )
    response.status_code = 202
    return CheckoutPendingResponse(checkout_id=checkout.id)


def create_order(
    current_user: dict, db: Session, response: Response, idempotency_key: UUID | None
):
    if response is None:
        response = Response()
    checkout_id, created = begin_checkout(db, current_user, idempotency_key)
    try:
        process_checkout(db, checkout_id)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            503,
            {"checkout_id": checkout_id, "message": "Reintentar con el mismo checkout"},
        ) from exc
    return checkout_result(db, checkout_id, current_user["id"], response, created)


def get_checkout(
    checkout_id: UUID, response: Response, current_user: dict, db: Session
):
    return checkout_result(db, str(checkout_id), current_user["id"], response)


def list_orders(
    skip: int,
    limit: int,
    order_status: (
        Literal[
            "PENDING",
            "CANCELLING",
            "CANCELLED",
            "PAID",
            "PROCESSING",
            "SHIPPED",
            "DELIVERED",
        ]
        | None
    ),
    current_user: dict,
    db: Session,
):
    rows = repository.list_owned(db, current_user["id"], skip, limit, order_status)
    payload = [
        OrderResponse.model_validate(row).model_dump(mode="json") for row in rows
    ]
    db.rollback()
    return payload


def cancel_order(order_id: int, response: Response, current_user: dict, db: Session):
    order = repository.get(db, order_id, current_user["id"], lock=True)
    if order is None:
        raise HTTPException(404, "La orden no existe")
    if order.status == "CANCELLED":
        return order
    if order.status not in ("PENDING", "CANCELLING"):
        raise HTTPException(
            409,
            "Solo se pueden cancelar pedidos pendientes; un pago confirmado requiere reembolso",
        )
    order.status = "CANCELLING"
    db.commit()
    order = finish_cancellation(db, order_id)
    if order.status not in ("CANCELLED", "CANCELLING"):
        raise HTTPException(
            409, "El pago se confirmo antes de la cancelacion; requiere reembolso"
        )
    if order.status == "CANCELLING":
        response.status_code = 202
    return order


def get_order(order_id: int, current_user: dict, db: Session):
    user_id = current_user["id"]
    order = repository.get(db, order_id, user_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="La orden no existe"
        )
    return order


def update_order_status(
    order_id: int, status_data: OrderStatusUpdate, current_user: dict, db: Session
):
    """
    Actualiza el estado administrativo de una orden.

    Restricciones:
    - Solo administradores.
    - PAID no puede establecerse manualmente.
    - Se respetan las transiciones autorizadas.
    """
    order = repository.get(db, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="La orden no existe"
        )
    requested_status = status_data.status
    if requested_status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El estado PAID solo puede establecerse mediante un pago verificado",
        )
    allowed_transitions = {
        "PENDING": set(),
        "PAID": {"PROCESSING"},
        "PROCESSING": {"SHIPPED"},
        "SHIPPED": {"DELIVERED"},
        "DELIVERED": set(),
        "CANCELLED": set(),
    }
    current_status = order.status
    if current_status not in allowed_transitions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La orden tiene un estado desconocido",
        )
    if requested_status not in allowed_transitions[current_status]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transicion no permitida: {current_status} -> {requested_status}",
        )
    order.status = requested_status
    db.commit()
    db.refresh(order)
    return order


def get_internal_order(order_id: int, db: Session):
    order = repository.get(db, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Orden no encontrada"
        )
    return {
        "order_id": order.id,
        "user_id": order.user_id,
        "status": order.status,
        "items": [
            {"product_id": item.product_id, "quantity": item.quantity}
            for item in order.items
        ],
    }

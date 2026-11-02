"""HTTP validation, authorization and response contracts for orders."""

from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app import order_actions as actions
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, Header
from typing import Literal, Annotated
from app.core.security import get_current_user, require_admin
from app.database import get_db
from app.schemas.order import CheckoutPendingResponse
from uuid import UUID
from app.schemas import OrderResponse, OrderStatusUpdate
from app.core.internal_security import verify_internal_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("/health")
def orders_health():
    return {"service": "Order Service", "status": "healthy"}


@router.post(
    "", response_model=OrderResponse | CheckoutPendingResponse, status_code=201
)
def create_order(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    response: Response = None,
    idempotency_key: Annotated[UUID | None, Header()] = None,
):
    return actions.create_order(current_user, db, response, idempotency_key)


@router.get(
    "/checkouts/{checkout_id}", response_model=OrderResponse | CheckoutPendingResponse
)
def get_checkout(
    checkout_id: UUID,
    response: Response,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return actions.get_checkout(checkout_id, response, current_user, db)


@router.get("", response_model=list[OrderResponse])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
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
    ) = Query(None, alias="status"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return JSONResponse(
        content=actions.list_orders(skip, limit, order_status, current_user, db)
    )


@router.get("/admin", response_model=list[OrderResponse])
def list_all_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    order_status: (
        Literal[
            "PENDING", "CANCELLING", "CANCELLED", "PAID",
            "PROCESSING", "SHIPPED", "DELIVERED",
        ]
        | None
    ) = Query(None, alias="status"),
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return JSONResponse(content=actions.list_all_orders(skip, limit, order_status, db))


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    responses={
        202: {
            "model": OrderResponse,
            "description": "Cancelacion pendiente de recuperacion",
        },
        409: {"description": "Pago confirmado o estado no cancelable"},
    },
)
def cancel_order(
    order_id: int,
    response: Response,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return actions.cancel_order(order_id, response, current_user, db)


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return actions.get_order(order_id, current_user, db)


@router.patch("/{order_id}/status", response_model=OrderResponse)
def update_order_status(
    order_id: int,
    status_data: OrderStatusUpdate,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return actions.update_order_status(order_id, status_data, current_user, db)


@router.get("/internal/{order_id}", dependencies=[Depends(verify_internal_service)])
def get_internal_order(order_id: int, db: Session = Depends(get_db)):
    return actions.get_internal_order(order_id, db)

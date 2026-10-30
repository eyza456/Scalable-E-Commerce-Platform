"""Payment HTTP validation, authorization and public response contracts."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from app.core.security import get_current_user
from app.database import get_db
from app.schemas import PaymentCreate, PaymentResponse
from app.core.internal_security import verify_internal_service
from app import payment_actions as actions

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get("/health")
def payment_health():
    return {"service": "Payment Service", "status": "healthy"}


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        202: {
            "model": PaymentResponse,
            "description": "Intento pendiente de reserva; recuperacion automatica",
        },
        409: {
            "description": "Pago rechazado, simulacion incompatible o intento historico incompatible"
        },
    },
)
def create_payment(
    payment_data: PaymentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    response: Response = None,
):
    return actions.create_payment(payment_data, current_user, db, response)


@router.get(
    "/internal/orders/{order_id}/cancellation",
    dependencies=[Depends(verify_internal_service)],
)
def get_order_cancellation(order_id: int, db: Session = Depends(get_db)):
    return actions.get_order_cancellation(order_id, db)


@router.post(
    "/internal/orders/{order_id}/cancel",
    dependencies=[Depends(verify_internal_service)],
)
def cancel_order_payments(
    order_id: int, response: Response, db: Session = Depends(get_db)
):
    return actions.cancel_order_payments(order_id, response, db)


@router.get("/orders/{order_id}/latest", response_model=PaymentResponse)
def get_latest_order_payment(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return actions.get_latest_order_payment(order_id, current_user, db)


@router.get("/transactions/{transaction_id}")
def get_payment_by_transaction(
    transaction_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return actions.get_payment_by_transaction(transaction_id, current_user, db)


@router.get(
    "/internal/transactions/{transaction_id}",
    dependencies=[Depends(verify_internal_service)],
)
def get_internal_payment_transaction(
    transaction_id: str, db: Session = Depends(get_db)
):
    return actions.get_internal_payment_transaction(transaction_id, db)

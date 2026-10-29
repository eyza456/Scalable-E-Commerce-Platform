import uuid

import httpx
from app import http_client

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from sqlalchemy import text
from app.inventory import settle_payment, REJECTION_MESSAGES
from app.database import get_db
from app.models import Payment, OrderCancellation
from app.cancellations import begin_cancellation, finish_cancellation
from app.schemas import PaymentCreate, PaymentResponse
from app.core.internal_security import verify_internal_service

router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)


@router.get("/health")
def payment_health():
    return {
        "service": "Payment Service",
        "status": "healthy"
    }


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        202: {"model": PaymentResponse, "description": "Intento pendiente de reserva; recuperacion automatica"},
        409: {"description": "Pago rechazado, simulacion incompatible o intento historico incompatible"},
    },
)
def create_payment(
    payment_data: PaymentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    response: Response = None,
):
    user_id = current_user["id"]
    token = current_user["token"]

    # ==========================================================
    # 1. CONSULTAR LA ORDEN
    # ==========================================================

    try:
        order_response = http_client.get(
            f"{settings.ORDER_SERVICE_URL}/orders/{payment_data.order_id}",
            headers={
                "Authorization": f"Bearer {token}"
            },
            timeout=10.0
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo conectar con Order Service"
        )

    if order_response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La orden no existe"
        )

    if order_response.status_code != 200:
        raise HTTPException(
            status_code=order_response.status_code,
            detail="No se pudo obtener la orden"
        )

    order = order_response.json()

    # ==========================================================
    # 2. VALIDAR PROPIETARIO DE LA ORDEN
    # ==========================================================

    if order["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para pagar esta orden"
        )

    # ==========================================================
    # 3. VALIDAR ESTADO DE LA ORDEN
    # ==========================================================

    if order["status"] != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La orden no está pendiente de pago"
        )

    # ==========================================================
    # 4. EVITAR DOBLE PAGO
    # ==========================================================

    # Serializar solicitudes de la misma orden incluso entre replicas.
    db.execute(
        text("SELECT pg_advisory_xact_lock(17001, :order_id)"),
        {"order_id": payment_data.order_id},
    )
    if db.get(OrderCancellation, payment_data.order_id):
        raise HTTPException(409, "La orden fue cancelada o esta en cancelacion")

    existing_payment = (
        db.query(Payment)
        .filter(
            Payment.order_id == payment_data.order_id,
            Payment.status.in_(("PENDING", "PAID"))
        )
        .first()
    )

    if existing_payment and existing_payment.status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La orden ya fue pagada"
        )

    if existing_payment and existing_payment.event_payload is None:
        raise HTTPException(409, "El intento historico no tiene snapshot de inventario; requiere revision")
    if existing_payment and existing_payment.simulation_result != payment_data.simulation_result:
        raise HTTPException(409, "El resultado simulado del intento pendiente no puede cambiar")

    # ==========================================================
    # 5. CREAR PAGO SIMULADO
    # ==========================================================

    transaction_id = (
        f"TX-{uuid.uuid4().hex[:12].upper()}"
    )

    payment = Payment(
        order_id=order["id"],
        user_id=user_id,
        amount=order["total"],
        method=payment_data.method,
        simulation_result=payment_data.simulation_result,
        status="PENDING",
        transaction_id=transaction_id
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
    # Persistir el intento antes de cualquier llamada al inventario.
    if existing_payment:
        payment = existing_payment
    else:
        payment.event_payload = event
        db.add(payment)
    try:
        db.commit()
        payment_id = payment.id
        db.rollback()  # cerrar lectura implicita antes del bloqueo de recuperacion
        payment = settle_payment(db, payment_id)
    except Exception:
        db.rollback()
        raise
    if payment.status == "REJECTED":
        code = payment.rejection_code or "INSUFFICIENT_STOCK"
        raise HTTPException(409, detail={
            "code": code, "transaction_id": payment.transaction_id,
            "message": REJECTION_MESSAGES[code],
        })
    if payment.status == "CANCELLED":
        raise HTTPException(409, "El pago fue cancelado junto con la orden")
    if payment.status == "PENDING" and response is not None:
        response.status_code = status.HTTP_202_ACCEPTED
    return payment


@router.get("/internal/orders/{order_id}/cancellation", dependencies=[Depends(verify_internal_service)])
def get_order_cancellation(order_id: int, db: Session = Depends(get_db)):
    cancellation = db.get(OrderCancellation, order_id)
    if cancellation is None:
        raise HTTPException(404, "Cancelacion no encontrada")
    return {"order_id": order_id, "user_id": cancellation.user_id, "status": cancellation.status}


@router.post("/internal/orders/{order_id}/cancel", dependencies=[Depends(verify_internal_service)])
def cancel_order_payments(order_id: int, response: Response, db: Session = Depends(get_db)):
    try:
        result = http_client.get(settings.ORDER_SERVICE_URL.rstrip("/") + f"/orders/internal/{order_id}",
                           headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY}, timeout=10)
        order = result.json()
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(503, "No se pudo verificar la orden") from exc
    if result.status_code != 200 or not isinstance(order, dict):
        raise HTTPException(503, "No se pudo verificar la orden")
    if order.get("order_id") != order_id or order.get("status") not in ("CANCELLING", "CANCELLED"):
        raise HTTPException(409, "La orden no tiene una cancelacion solicitada")
    begin_cancellation(db, order_id, order["user_id"])
    cancellation = finish_cancellation(db, order_id)
    if cancellation.status != "DONE":
        response.status_code = 202
    return {"order_id": order_id, "user_id": cancellation.user_id, "status": cancellation.status}


@router.get("/orders/{order_id}/latest", response_model=PaymentResponse)
def get_latest_order_payment(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Filtrar por propietario en SQL: no revelar intentos de pedidos ajenos.
    payment = (db.query(Payment)
               .filter(Payment.order_id == order_id, Payment.user_id == current_user["id"])
               .order_by(Payment.id.desc()).first())
    if payment is None:
        raise HTTPException(404, "No hay intentos de pago para este pedido")
    return payment


@router.get("/transactions/{transaction_id}")
def get_payment_by_transaction(
    transaction_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    payment = (
        db.query(Payment)
        .filter(Payment.transaction_id == transaction_id)
        .first()
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaccion no encontrada"
        )

    if payment.user_id != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para consultar esta transaccion"
        )

    return {
        "transaction_id": payment.transaction_id,
        "order_id": payment.order_id,
        "status": payment.status,
        "amount": float(payment.amount),
        "processed_at": payment.processed_at,
        "rejection_code": payment.rejection_code,
        "method": payment.method
    }


@router.get(
    "/internal/transactions/{transaction_id}",
    dependencies=[Depends(verify_internal_service)]
)
def get_internal_payment_transaction(
    transaction_id: str,
    db: Session = Depends(get_db)
):
    payment = (
        db.query(Payment)
        .filter(Payment.transaction_id == transaction_id)
        .first()
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaccion no encontrada"
        )

    return {
        "transaction_id": payment.transaction_id,
        "order_id": payment.order_id,
        "user_id": payment.user_id,
        "status": payment.status,
        "processed_at": payment.processed_at,
        "rejection_code": payment.rejection_code,
        "items": (payment.event_payload or {}).get("items"),
        "inventory_reservation_id": (payment.event_payload or {}).get("inventory_reservation_id"),
        "amount": str(payment.amount)
    }

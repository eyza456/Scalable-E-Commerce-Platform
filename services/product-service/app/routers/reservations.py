import os
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InventoryReservation
from app.reservations import reserve, release, StockUnavailable, ReservationConflict
from app.services.payment_validation import (
    internal_get, TemporaryValidationError, PermanentValidationError,
)

key_header = APIKeyHeader(name="X-Internal-Service-Key", auto_error=False)


def internal_only(key: str | None = Security(key_header)):
    expected = os.getenv("INTERNAL_SERVICE_KEY")
    if not expected or not key or not secrets.compare_digest(key, expected):
        raise HTTPException(403, "Acceso interno no autorizado")


router = APIRouter(prefix="/inventory/internal/reservations", tags=["Inventory"],
                   dependencies=[Depends(internal_only)])

release_router = APIRouter(prefix="/inventory/internal/orders", tags=["Inventory"],
                          dependencies=[Depends(internal_only)])


@release_router.post("/{order_id}/release")
def release_order(order_id: int, db: Session = Depends(get_db)):
    try:
        _, cancellation = internal_get(os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8000"),
                                       f"/payments/internal/orders/{order_id}/cancellation")
        if cancellation.get("order_id") != order_id or cancellation.get("status") not in ("PENDING", "DONE"):
            raise HTTPException(409, "Cancelacion no verificada")
        release(db, order_id)
        db.commit()
        return {"order_id": order_id, "status": "RELEASED"}
    except (ReservationConflict, PermanentValidationError) as exc:
        db.rollback()
        raise HTTPException(409, "No se pudo liberar la reserva") from exc
    except TemporaryValidationError as exc:
        db.rollback()
        raise HTTPException(503, "Cancelacion temporalmente no verificable") from exc


@router.post("/{transaction_id}")
def reserve_for_payment(transaction_id: str, db: Session = Depends(get_db)):
    """Lee el intento durable en Payment, sin aceptar cantidades del cliente."""
    try:
        _, payment = internal_get(os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8000"),
                                  "/payments/internal/transactions/" + quote(transaction_id, safe=""))
        if payment.get("transaction_id") != transaction_id or payment.get("status") not in ("PENDING", "PAID"):
            raise HTTPException(409, "El pago no permite reservar inventario")
        # Una confirmacion HTTP perdida se recupera devolviendo la misma reserva.
        existing = db.get(InventoryReservation, transaction_id)
        if payment["status"] == "PAID" and existing is None:
            raise HTTPException(409, "Pago confirmado sin reserva; requiere revision")
        reservation = reserve(db, transaction_id, payment["order_id"], payment["user_id"], payment.get("items"))
        db.commit()
        return {"reservation_id": reservation.transaction_id, "status": reservation.status}
    except StockUnavailable as exc:
        db.rollback()
        raise HTTPException(409, {"code": "INSUFFICIENT_STOCK", "message": str(exc)}) from exc
    except (ReservationConflict, ValueError, PermanentValidationError) as exc:
        db.rollback()
        raise HTTPException(409, {"code": "RESERVATION_CONFLICT", "message": str(exc)}) from exc
    except TemporaryValidationError as exc:
        db.rollback()
        raise HTTPException(503, "No se pudo verificar el intento de pago") from exc

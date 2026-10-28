"""El stock representa unidades disponibles: reservar ya las retira del catalogo."""
from sqlalchemy import text, update

from app.models import Product, ProcessedPaymentEvent, InventoryReservation, InventoryCancellation
from app.services.payment_validation import normalize_items


class StockUnavailable(Exception):
    pass


class ReservationConflict(Exception):
    pass


def reserve(db, transaction_id, order_id, user_id, items):
    """Reserva todos los items o ninguno. El llamador confirma la transaccion."""
    normalized = normalize_items(items)
    db.execute(text("SELECT pg_advisory_xact_lock(17002, :id)"), {"id": order_id})
    if db.get(InventoryCancellation, order_id):
        raise ReservationConflict("El pedido ya no admite reservas")
    existing = db.query(InventoryReservation).filter_by(order_id=order_id).first()
    if existing:
        if (existing.transaction_id != transaction_id or existing.user_id != user_id
                or normalize_items(existing.items) != normalized):
            raise ReservationConflict("La orden ya tiene otra reserva")
        return existing
    if db.query(ProcessedPaymentEvent).filter_by(order_id=order_id).first():
        raise ReservationConflict("La orden ya desconto inventario")

    for product_id, quantity in sorted(normalized.items()):
        result = db.execute(
            update(Product)
            .where(Product.id == product_id, Product.stock >= quantity, Product.is_active.is_(True))
            .values(stock=Product.stock - quantity)
        )
        if result.rowcount != 1:
            raise StockUnavailable(f"Producto #{product_id} sin disponibilidad suficiente")
    reservation = InventoryReservation(
        transaction_id=transaction_id, order_id=order_id, user_id=user_id,
        items=[{"product_id": p, "quantity": q} for p, q in sorted(normalized.items())],
        status="RESERVED",
    )
    db.add(reservation)
    db.flush()
    return reservation


def release(db, order_id):
    """Libera todo o nada; la barrera bloquea solicitudes de reserva tardias."""
    db.execute(text("SELECT pg_advisory_xact_lock(17002, :id)"), {"id": order_id})
    reservation = db.query(InventoryReservation).filter_by(order_id=order_id).with_for_update().first()
    if reservation and reservation.status == "CONSUMED":
        raise ReservationConflict("La reserva pertenece a un pago confirmado")
    if reservation and reservation.status == "RESERVED":
        for product_id, quantity in sorted(normalize_items(reservation.items).items()):
            result = db.execute(update(Product).where(Product.id == product_id)
                                .values(stock=Product.stock + quantity))
            if result.rowcount != 1:
                raise ReservationConflict("No se puede liberar un producto inexistente")
        reservation.status = "RELEASED"
    elif reservation and reservation.status != "RELEASED":
        raise ReservationConflict("Estado de reserva desconocido")
    if db.get(InventoryCancellation, order_id) is None:
        db.add(InventoryCancellation(order_id=order_id))
    db.flush()


def consume(db, message, normalized):
    """Confirma una reserva sin volver a descontar stock."""
    transaction_id = message["transaction_id"]
    if message["inventory_reservation_id"] != transaction_id:
        raise ValueError("Identificador de reserva inconsistente")
    reservation = (
        db.query(InventoryReservation)
        .filter_by(transaction_id=transaction_id).with_for_update().first()
    )
    if (reservation is None or reservation.order_id != message["order_id"]
            or reservation.user_id != message.get("user_id")
            or normalize_items(reservation.items) != normalized
            or reservation.status not in ("RESERVED", "CONSUMED")):
        raise ValueError("El pago no coincide con una reserva valida")
    reservation.status = "CONSUMED"

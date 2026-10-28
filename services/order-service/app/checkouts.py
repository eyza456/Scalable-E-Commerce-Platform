"""Checkout durable por version del carrito, con finalizacion recuperable."""
import logging
from decimal import Decimal, InvalidOperation
from uuid import UUID

import httpx
from app import http_client
from fastapi import HTTPException
from sqlalchemy import text

from app.core.config import settings
from app.database import SessionLocal
from app.models import Checkout, Order, OrderItem

logger = logging.getLogger(__name__)


class Unavailable(Exception):
    pass


class Rejected(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def lock_user(db, user_id, skip=False):
    function = "pg_try_advisory_xact_lock" if skip else "pg_advisory_xact_lock"
    result = db.execute(text(f"SELECT {function}(17003, :id)"), {"id": user_id}).scalar()
    return bool(result) if skip else True


def cart_call(checkout, action):
    try:
        response = http_client.post(
            settings.CART_SERVICE_URL.rstrip("/") + f"/cart/internal/{checkout.user_id}/checkout/{checkout.id}/{action}",
            headers={"X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY}, timeout=5,
        )
        data = response.json()
    except (httpx.RequestError, ValueError) as exc:
        raise Unavailable("Carrito temporalmente no disponible") from exc
    if action == "prepare" and response.status_code == 409:
        raise Rejected("STALE_CART", "El carrito cambio; actualizar antes de confirmar")
    if response.status_code != 200 or not isinstance(data, dict):
        raise Unavailable("No se pudo coordinar el carrito")
    if action != "prepare":
        expected = "COMMITTED" if action == "commit" else "ABORTED"
        if data.get("checkout_id") != checkout.id or data.get("state") != expected:
            raise Unavailable("Confirmacion de carrito invalida")
    return data


def validate_products(snapshot):
    items, total = [], Decimal("0.00")
    if not isinstance(snapshot.get("items"), list) or not snapshot["items"]:
        raise Rejected("EMPTY_CART", "No se puede crear una orden con el carrito vacio")
    seen = set()
    for item in snapshot["items"]:
        try:
            product_id, quantity = item["product_id"], item["quantity"]
            old_price = Decimal(str(item["price"]))
            if (type(product_id) is not int or product_id <= 0 or product_id in seen
                    or type(quantity) is not int or not 1 <= quantity <= 100 or not old_price.is_finite()):
                raise ValueError()
            seen.add(product_id)
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            raise Rejected("INVALID_CART", "Datos de carrito invalidos") from exc
        try:
            response = http_client.get(f"{settings.PRODUCT_SERVICE_URL}/products/{product_id}", timeout=5)
            product = response.json()
        except (httpx.RequestError, ValueError) as exc:
            raise Unavailable("Catalogo temporalmente no disponible") from exc
        if response.status_code == 404:
            raise Rejected("PRODUCT_UNAVAILABLE", "Un producto ya no existe")
        if response.status_code != 200 or not isinstance(product, dict):
            raise Unavailable("No se pudo consultar el catalogo")
        if not product.get("is_active"):
            raise Rejected("PRODUCT_UNAVAILABLE", "Un producto esta inactivo")
        if product["stock"] < quantity:
            raise Rejected("INSUFFICIENT_STOCK", "Un producto no tiene stock suficiente")
        price = Decimal(str(product["price"]))
        if price != old_price:
            raise Rejected("PRICE_CHANGED", "Cambio el precio; actualizar el item del carrito y confirmar de nuevo")
        subtotal = price * quantity
        total += subtotal
        items.append(dict(product_id=product_id, product_name=product["name"],
                          quantity=quantity, price=price, subtotal=subtotal))
    if not total.is_finite() or total <= 0 or total > Decimal("99999999.99"):
        raise Rejected("INVALID_TOTAL", "El total excede el limite admitido")
    return items, total


def process_checkout(db, checkout_id, skip=False):
    initial = db.get(Checkout, checkout_id)
    if initial is None:
        return
    user_id = initial.user_id
    # Cada commit es un punto de recuperacion; volver a bloquear antes de avanzar.
    while True:
        if not lock_user(db, user_id, skip):
            db.rollback()
            return
        checkout = db.query(Checkout).filter_by(id=checkout_id).with_for_update().populate_existing().one()
        try:
            if checkout.state in ("COMPLETE", "REJECTED"):
                db.commit()
                return
            if checkout.state in ("FINALIZING", "ABORTING"):
                committed = checkout.state == "FINALIZING"
                cart_call(checkout, "commit" if committed else "abort")
                checkout.state = "COMPLETE" if committed else "REJECTED"
                db.commit()
                return
            snapshot = cart_call(checkout, "prepare")
            if (snapshot.get("user_id") != user_id or snapshot.get("version") != checkout.id
                    or snapshot.get("checkout_id") != checkout.id):
                raise Unavailable("Snapshot de carrito no verificable")
            items, total = validate_products(snapshot)
            order = Order(user_id=user_id, checkout_id=checkout.id, total=total, status="PENDING",
                          items=[OrderItem(**item) for item in items])
            db.add(order)
            db.flush()
            checkout.order_id, checkout.state = order.id, "FINALIZING"
            db.commit()
        except Rejected as exc:
            checkout.state = "ABORTING"
            checkout.error_code, checkout.error_message = exc.code, exc.message
            db.commit()
        except Unavailable as exc:
            db.rollback()
            logger.warning("Checkout %s pendiente: %s", checkout_id, exc)
            return
        except Exception:
            db.rollback()
            raise


def begin_checkout(db, current_user, key=None):
    user_id = current_user["id"]
    lock_user(db, user_id)
    if key:
        checkout = db.get(Checkout, str(key))
        if checkout is not None:
            if checkout.user_id != user_id:
                raise HTTPException(404, "Checkout no encontrado")
            db.commit()
            return checkout.id, False
    active = db.query(Checkout).filter(Checkout.user_id == user_id,
        Checkout.state.in_(("PENDING", "FINALIZING", "ABORTING"))).first()
    if active:
        if key and str(key) != active.id:
            raise HTTPException(409, "Ya existe un checkout en curso")
        db.commit()
        return active.id, False
    try:
        response = http_client.get(f"{settings.CART_SERVICE_URL}/cart",
                            headers={"Authorization": f"Bearer {current_user['token']}"}, timeout=5)
        cart = response.json()
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(503, "Carrito no disponible") from exc
    if response.status_code != 200:
        raise HTTPException(response.status_code, "No se pudo consultar el carrito")
    if not cart.get("items"):
        previous = db.get(Checkout, cart.get("last_checkout_id")) if cart.get("last_checkout_id") else None
        if previous is not None and previous.user_id == user_id and previous.order_id is not None and not key:
            db.commit()
            return previous.id, False
        raise HTTPException(400, "No se puede crear una orden con el carrito vacio")
    try:
        version = str(UUID(cart["version"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(503, "Version del carrito no verificable") from exc
    if key and str(key) != version:
        raise HTTPException(409, "La version del carrito cambio")
    checkout = db.get(Checkout, version)
    created = checkout is None
    if created:
        db.add(Checkout(id=version, user_id=user_id, state="PENDING"))
    elif checkout.user_id != user_id:
        raise HTTPException(404, "Checkout no encontrado")
    db.commit()
    return version, created


def recover_checkouts():
    with SessionLocal() as db:
        ids = [r[0] for r in db.query(Checkout.id).filter(Checkout.state.in_(("PENDING", "FINALIZING", "ABORTING"))).all()]
    for checkout_id in ids:
        try:
            with SessionLocal() as db:
                process_checkout(db, checkout_id, skip=True)
        except Exception:
            logger.exception("No se pudo recuperar checkout %s", checkout_id)


def run_recovery(stop):
    while not stop.is_set():
        try:
            recover_checkouts()
        except Exception:
            logger.exception("Recuperador de checkout no disponible")
        stop.wait(5)

"""Local order persistence; no remote service access or transaction commits."""

from sqlalchemy.orm import selectinload
from app.models import Order, Checkout


def checkout(db, checkout_id):
    return db.get(Checkout, checkout_id)


def get(db, order_id, user_id=None, *, lock=False, eager=False):
    query = db.query(Order).filter(Order.id == order_id)
    if user_id is not None:
        query = query.filter(Order.user_id == user_id)
    if lock:
        query = query.with_for_update()
    if eager:
        query = query.options(selectinload(Order.items))
    return query.first()


def list_owned(db, user_id, skip, limit, status=None):
    query = (
        db.query(Order)
        .options(selectinload(Order.items))
        .filter(Order.user_id == user_id)
    )
    if status is not None:
        query = query.filter(Order.status == status)
    return (
        query.order_by(Order.created_at.desc(), Order.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

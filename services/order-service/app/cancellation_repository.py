"""Persistencia local de recuperaciones de cancelaciones."""

from sqlalchemy.orm import Session

from app.models import Order


def pending_ids(db: Session) -> list[int]:
    return [row[0] for row in db.query(Order.id).filter_by(status="CANCELLING").all()]


def lock(db: Session, order_id: int) -> Order | None:
    return (
        db.query(Order)
        .filter_by(id=order_id)
        .with_for_update()
        .populate_existing()
        .first()
    )

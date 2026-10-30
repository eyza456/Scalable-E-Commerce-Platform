"""Local payment persistence. Callers own commits and business decisions."""

from sqlalchemy import text
from app.models import Payment, OrderCancellation, OutboxEvent


def lock_order(db, order_id, *, skip=False):
    fn = "pg_try_advisory_xact_lock" if skip else "pg_advisory_xact_lock"
    value = db.execute(text(f"SELECT {fn}(17001, :id)"), {"id": order_id}).scalar()
    return bool(value) if skip else True


def cancellation(db, order_id):
    return db.get(OrderCancellation, order_id)


def locked_cancellation(db, order_id, *, skip=False):
    return (
        db.query(OrderCancellation)
        .filter_by(order_id=order_id)
        .with_for_update(skip_locked=skip)
        .populate_existing()
        .first()
    )


def active_payment(db, order_id):
    return (
        db.query(Payment)
        .filter(Payment.order_id == order_id, Payment.status.in_(("PENDING", "PAID")))
        .first()
    )


def has_paid(db, order_id):
    return (
        db.query(Payment.id).filter_by(order_id=order_id, status="PAID").first()
        is not None
    )


def latest_owned(db, order_id, user_id):
    return (
        db.query(Payment)
        .filter(Payment.order_id == order_id, Payment.user_id == user_id)
        .order_by(Payment.id.desc())
        .first()
    )


def by_transaction(db, transaction_id):
    return db.query(Payment).filter(Payment.transaction_id == transaction_id).first()


def order_for_payment(db, payment_id):
    return db.query(Payment.order_id).filter_by(id=payment_id).scalar()


def locked_payment(db, payment_id, *, skip=False):
    return (
        db.query(Payment)
        .filter_by(id=payment_id)
        .with_for_update(skip_locked=skip)
        .populate_existing()
        .first()
    )


def pending_payment_ids(db):
    return [
        r[0]
        for r in db.query(Payment.id)
        .filter(Payment.status == "PENDING", Payment.event_payload.is_not(None))
        .order_by(Payment.id)
        .all()
    ]


def pending_cancellation_ids(db):
    return [
        r[0]
        for r in db.query(OrderCancellation.order_id).filter_by(status="PENDING").all()
    ]


def cancel_pending(db, order_id, processed_at):
    db.query(Payment).filter_by(order_id=order_id, status="PENDING").update(
        {"status": "CANCELLED", "processed_at": processed_at}, synchronize_session=False
    )


def pending_events(db, limit):
    return (
        db.query(OutboxEvent)
        .filter(OutboxEvent.status == "PENDING")
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )

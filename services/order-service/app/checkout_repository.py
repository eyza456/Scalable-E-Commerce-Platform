"""Local checkout persistence and coordination locks."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Checkout


def lock_user(db: Session, user_id: int, skip: bool = False) -> bool:
    function = "pg_try_advisory_xact_lock" if skip else "pg_advisory_xact_lock"
    result = db.execute(text(f"SELECT {function}(17003, :id)"), {"id": user_id}).scalar()
    return bool(result) if skip else True


def get(db: Session, checkout_id: str) -> Checkout | None:
    return db.get(Checkout, checkout_id)


def lock(db: Session, checkout_id: str) -> Checkout:
    return (
        db.query(Checkout)
        .filter_by(id=checkout_id)
        .with_for_update()
        .populate_existing()
        .one()
    )


def active_for_user(db: Session, user_id: int) -> Checkout | None:
    return (
        db.query(Checkout)
        .filter(
            Checkout.user_id == user_id,
            Checkout.state.in_(("PENDING", "FINALIZING", "ABORTING")),
        )
        .first()
    )


def pending_ids(db: Session) -> list[str]:
    return [
        row[0]
        for row in db.query(Checkout.id)
        .filter(Checkout.state.in_(("PENDING", "FINALIZING", "ABORTING")))
        .all()
    ]


def add(db: Session, checkout: Checkout) -> Checkout:
    db.add(checkout)
    return checkout


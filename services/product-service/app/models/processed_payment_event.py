
from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class ProcessedPaymentEvent(Base):
    __tablename__ = "processed_payment_events"

    __table_args__ = (
        Index(
            "ux_processed_payment_events_order_id",
            "order_id",
            unique=True
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    transaction_id = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    order_id = Column(
        Integer,
        nullable=False
    )

    processed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

from app.database import Base


class ProcessedPaymentEvent(Base):
    __tablename__ = "processed_payment_events"

    id = Column(Integer, primary_key=True, index=True)

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
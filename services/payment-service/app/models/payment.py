from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, Numeric, String, JSON

from app.database import Base


class Payment(Base):

    __tablename__ = "payments"

    # Snapshot persistido ANTES de cualquier llamada al inventario.
    # NULL identifica pagos historicos, que no se recuperan como intentos nuevos.
    event_payload = Column(JSON, nullable=True)

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    order_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    user_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    amount = Column(
        Numeric(10, 2),
        nullable=False
    )

    method = Column(
        String(50),
        nullable=False
    )

    status = Column(
        String(30),
        nullable=False,
        default="PENDING"
    )

    transaction_id = Column(
        String(100),
        nullable=True,
        unique=True
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

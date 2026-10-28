import uuid

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
)

from app.database import Base


class OutboxEvent(Base):

    __tablename__ = "outbox_events"

    destination = Column(String(100), nullable=False, index=True)

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    event_type = Column(
        String(100),
        nullable=False,
        index=True
    )

    aggregate_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    payload = Column(
        JSON,
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        index=True
    )

    attempts = Column(
        Integer,
        nullable=False,
        default=0
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    published_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    last_error = Column(
        Text,
        nullable=True
    )

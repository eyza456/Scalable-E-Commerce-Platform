from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Order(Base):

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_created_id", "user_id", "created_at", "id"),
    )
    checkout_id = Column(String(36), nullable=True, unique=True)

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    status = Column(
        String(30),
        nullable=False,
        default="PENDING"
    )

    total = Column(
        Numeric(10, 2),
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan"
    )


class OrderItem(Base):

    __tablename__ = "order_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    order_id = Column(
        Integer,
        ForeignKey("orders.id"),
        nullable=False
    )

    product_id = Column(
        Integer,
        nullable=False
    )

    product_name = Column(
        String(200),
        nullable=False
    )

    quantity = Column(
        Integer,
        nullable=False
    )

    price = Column(
        Numeric(10, 2),
        nullable=False
    )

    subtotal = Column(
        Numeric(10, 2),
        nullable=False
    )

    order = relationship(
        "Order",
        back_populates="items"
    )


class Checkout(Base):
    __tablename__ = "checkouts"
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    state = Column(String(20), nullable=False, default="PENDING", index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=True)
    error_code = Column(String(50), nullable=True)
    error_message = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

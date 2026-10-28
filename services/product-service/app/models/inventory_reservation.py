from sqlalchemy import Column, DateTime, Integer, JSON, String
from sqlalchemy.sql import func

from app.database import Base


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"

    transaction_id = Column(String(100), primary_key=True)
    order_id = Column(Integer, nullable=False, unique=True)
    user_id = Column(Integer, nullable=False)
    items = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="RESERVED")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

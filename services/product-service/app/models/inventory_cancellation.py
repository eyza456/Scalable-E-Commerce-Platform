from sqlalchemy import Column, Integer
from app.database import Base


class InventoryCancellation(Base):
    """Barrera persistente que impide una reserva tardia tras liberar."""
    __tablename__ = "inventory_cancellations"
    order_id = Column(Integer, primary_key=True)

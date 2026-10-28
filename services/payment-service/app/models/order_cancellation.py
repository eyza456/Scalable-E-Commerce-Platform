from sqlalchemy import Column, Integer, String
from app.database import Base


class OrderCancellation(Base):
    __tablename__ = "order_cancellations"
    order_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")

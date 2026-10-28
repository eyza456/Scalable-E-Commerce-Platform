from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String(150),
        nullable=False,
        index=True
    )

    description = Column(
        Text,
        nullable=True
    )

    price = Column(
        Numeric(10, 2),
        nullable=False
    )

    stock = Column(
        Integer,
        nullable=False,
        default=0
    )

    category_id = Column(Integer, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True, index=True)
    category_record = relationship("Category", lazy="joined")

    @property
    def category(self):
        return self.category_record.name if self.category_record else None

    image_url = Column(
        String(500),
        nullable=True
    )

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True
    )

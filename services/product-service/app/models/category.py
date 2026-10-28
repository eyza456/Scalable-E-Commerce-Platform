from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func

from app.database import Base


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (Index("ux_categories_name_lower", func.lower(name), unique=True),)

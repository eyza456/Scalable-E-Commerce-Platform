
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Index
from sqlalchemy.sql import func
from app.database import Base 


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String(100),
        nullable=False
    )

    email = Column(
        String(150),
        unique=True,
        index=True,
        nullable=False
    )
    __table_args__ = (Index("ux_users_email_lower", func.lower(email), unique=True),)

    password_hash = Column(
        String(250),
        nullable=False
    )

    role = Column(
        String(50),
        default="Customer",
        nullable=False
    
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )

    create_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
        
    )

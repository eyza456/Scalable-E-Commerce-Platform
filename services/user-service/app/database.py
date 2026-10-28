from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base,sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL
)


SeccionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SeccionLocal()

    try:
        yield db
    finally:
        db.close()

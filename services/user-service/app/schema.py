"""Explicit startup schema bootstrap. Product schema uses Alembic separately."""


def initialize_schema():
    from app.database import Base, engine
    from app import models

    Base.metadata.create_all(bind=engine)

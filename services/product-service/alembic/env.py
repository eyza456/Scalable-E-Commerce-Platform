
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy import create_engine

from app.core.config import settings
from app.database import Base

# Importar los modelos para registrarlos en Base.metadata
from app.models import Product, ProcessedPaymentEvent, InventoryReservation


config = context.config

# Configurar logging de Alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadatos de los modelos SQLAlchemy
target_metadata = Base.metadata
MANAGED_TABLES = {
    "products",
    "processed_payment_events",
    "inventory_reservations",
    "categories",
    "inventory_cancellations",
}


def include_name(name, type_, parent_names):
    if type_ == "table":
        return name in MANAGED_TABLES

    return True


def run_migrations_offline() -> None:
    """
    Generar SQL sin conectarse directamente
    a la base de datos.
    """
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Ejecutar migraciones conectándose a PostgreSQL.
    """
    connectable = create_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                include_name=include_name,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

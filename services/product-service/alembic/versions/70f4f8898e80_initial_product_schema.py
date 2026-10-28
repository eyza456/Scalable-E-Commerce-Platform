
"""Initial Product Service schema.

Revision ID: 70f4f8898e80
Revises:
Create Date: 2026-10-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Alembic revision identifiers
revision: str = "70f4f8898e80"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =====================================
    # PRODUCTS
    # =====================================

    op.create_table(
        "products",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False
        ),

        sa.Column(
            "name",
            sa.String(length=150),
            nullable=False
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True
        ),

        sa.Column(
            "price",
            sa.Numeric(precision=10, scale=2),
            nullable=False
        ),

        sa.Column(
            "stock",
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            "category",
            sa.String(length=100),
            nullable=True
        ),

        sa.Column(
            "image_url",
            sa.String(length=500),
            nullable=True
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=True
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True
        ),
    )

    op.create_index(
        "ix_products_id",
        "products",
        ["id"],
        unique=False
    )

    op.create_index(
        "ix_products_name",
        "products",
        ["name"],
        unique=False
    )

    op.create_index(
        "ix_products_category",
        "products",
        ["category"],
        unique=False
    )

    # =====================================
    # PROCESSED PAYMENT EVENTS
    # =====================================

    op.create_table(
        "processed_payment_events",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False
        ),

        sa.Column(
            "transaction_id",
            sa.String(length=100),
            nullable=False
        ),

        sa.Column(
            "order_id",
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
    )

    op.create_index(
        "ix_processed_payment_events_id",
        "processed_payment_events",
        ["id"],
        unique=False
    )

    op.create_index(
        "ix_processed_payment_events_transaction_id",
        "processed_payment_events",
        ["transaction_id"],
        unique=True
    )

    op.create_index(
        "ux_processed_payment_events_order_id",
        "processed_payment_events",
        ["order_id"],
        unique=True
    )


def downgrade() -> None:
    # ADVERTENCIA:
    # El downgrade elimina tablas y sus datos.
    # No ejecutarlo sobre la base de datos actual.

    op.drop_index(
        "ux_processed_payment_events_order_id",
        table_name="processed_payment_events"
    )

    op.drop_index(
        "ix_processed_payment_events_transaction_id",
        table_name="processed_payment_events"
    )

    op.drop_index(
        "ix_processed_payment_events_id",
        table_name="processed_payment_events"
    )

    op.drop_table("processed_payment_events")

    op.drop_index(
        "ix_products_category",
        table_name="products"
    )

    op.drop_index(
        "ix_products_name",
        table_name="products"
    )

    op.drop_index(
        "ix_products_id",
        table_name="products"
    )

    op.drop_table("products")

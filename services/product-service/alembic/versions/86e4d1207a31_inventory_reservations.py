"""Reservas de inventario por intento de pago."""
from alembic import op
import sqlalchemy as sa

revision = "86e4d1207a31"
down_revision = "70f4f8898e80"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_reservations",
        sa.Column("transaction_id", sa.String(100), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("inventory_reservations")

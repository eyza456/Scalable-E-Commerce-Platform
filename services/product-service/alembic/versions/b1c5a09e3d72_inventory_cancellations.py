"""Barrera durable contra reservas de pedidos cancelados."""
from alembic import op
import sqlalchemy as sa

revision = "b1c5a09e3d72"
down_revision = "9b72ca103d45"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("inventory_cancellations", sa.Column("order_id", sa.Integer(), primary_key=True))


def downgrade():
    op.drop_table("inventory_cancellations")

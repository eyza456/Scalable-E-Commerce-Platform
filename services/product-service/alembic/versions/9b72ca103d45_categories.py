"""Categorias relacionadas, preservando los nombres existentes."""
from alembic import op
import sqlalchemy as sa

revision = "9b72ca103d45"
down_revision = "86e4d1207a31"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ux_categories_name_lower", "categories", [sa.text("lower(name)")], unique=True)
    op.add_column("products", sa.Column("category_id", sa.Integer(), nullable=True))
    op.execute("""INSERT INTO categories(name)
        SELECT min(btrim(category)) FROM products
        WHERE category IS NOT NULL AND btrim(category) <> ''
        GROUP BY lower(btrim(category)) ORDER BY lower(btrim(category))""")
    op.execute("""UPDATE products p SET category_id=c.id FROM categories c
        WHERE lower(btrim(p.category))=lower(c.name)""")
    op.create_foreign_key("fk_products_category", "products", "categories", ["category_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.drop_index("ix_products_category", table_name="products")
    op.drop_column("products", "category")


def downgrade():
    op.add_column("products", sa.Column("category", sa.String(100), nullable=True))
    op.execute("UPDATE products p SET category=c.name FROM categories c WHERE p.category_id=c.id")
    op.create_index("ix_products_category", "products", ["category"])
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_constraint("fk_products_category", "products", type_="foreignkey")
    op.drop_column("products", "category_id")
    op.drop_table("categories")

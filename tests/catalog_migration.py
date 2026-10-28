"""Verifica upgrade/downgrade con datos antiguos en un esquema propio."""
import importlib.util
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from app.database import engine


schema = "test_catalog_migration_" + uuid.uuid4().hex
path = Path("/app/alembic/versions/9b72ca103d45_categories.py")
spec = importlib.util.spec_from_file_location("catalog_revision", path)
revision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revision)
with engine.begin() as conn:
    conn.execute(text(f'CREATE SCHEMA "{schema}"'))
try:
    with engine.begin() as conn:
        conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        conn.execute(text("CREATE TABLE products(id SERIAL PRIMARY KEY, category VARCHAR(100))"))
        conn.execute(text("CREATE INDEX ix_products_category ON products(category)"))
        conn.execute(text("INSERT INTO products(category) VALUES (' Books '), ('books'), (''), (NULL), ('Hardware')"))
        with Operations.context(MigrationContext.configure(conn)):
            revision.upgrade()
        rows = conn.execute(text("SELECT p.id, c.name FROM products p LEFT JOIN categories c ON p.category_id=c.id ORDER BY p.id")).all()
        assert len(rows) == 5
        assert rows[0][1].lower() == rows[1][1].lower() == "books"
        assert rows[2][1] is None and rows[3][1] is None
        assert rows[4][1] == "Hardware"
        assert conn.execute(text("SELECT count(*) FROM categories")).scalar() == 2
        with Operations.context(MigrationContext.configure(conn)):
            revision.downgrade()
        names = conn.execute(text("SELECT category FROM products ORDER BY id")).scalars().all()
        assert names == [rows[0][1], rows[1][1], None, None, "Hardware"]
        print("OK: migracion y rollback conservan productos y categorias, agrupando duplicados.")
finally:
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))

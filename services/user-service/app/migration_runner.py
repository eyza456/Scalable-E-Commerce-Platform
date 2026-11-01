"""Ordered, repeatable SQL migrations for user-service."""

from pathlib import Path

from sqlalchemy import text

from app.database import engine


MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def apply_migrations() -> list[str]:
    applied: list[str] = []
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "migration_key VARCHAR(255) PRIMARY KEY, "
                "applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )
        known = {
            row[0]
            for row in connection.execute(text("SELECT migration_key FROM schema_migrations"))
        }
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in known:
                continue
            script = path.read_text(encoding="utf-8").replace("BEGIN;", "").replace("COMMIT;", "")
            connection.exec_driver_sql(script)
            connection.execute(
                text("INSERT INTO schema_migrations (migration_key) VALUES (:key)"),
                {"key": path.name},
            )
            applied.append(path.name)
    return applied


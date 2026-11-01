import unittest

from sqlalchemy import text

from app.database import engine
from app.migration_runner import MIGRATIONS, apply_migrations


class MigrationStability(unittest.TestCase):
    def test_migrations_are_versioned_and_idempotent(self):
        self.assertEqual(apply_migrations(), [])
        self.assertEqual(apply_migrations(), [])
        expected = sorted(path.name for path in MIGRATIONS.glob("*.sql"))
        with engine.connect() as connection:
            applied = [
                row[0]
                for row in connection.execute(
                    text("SELECT migration_key FROM schema_migrations ORDER BY migration_key")
                )
            ]
        self.assertEqual(applied, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)

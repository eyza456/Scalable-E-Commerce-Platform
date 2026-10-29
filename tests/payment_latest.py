"""Read-only latest-payment lookup: real isolated PostgreSQL schema."""
import unittest
import uuid

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, engine as production_engine
from app.models import Payment
from app.routers.payments import get_latest_order_payment


class LatestPayment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_latest_" + uuid.uuid4().hex
        with production_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.engine = create_engine(production_engine.url, connect_args={"options": f"-csearch_path={cls.schema}"})
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with production_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))

    def setUp(self):
        self.db = self.sessions()
        self.addCleanup(self.db.close)
        self.db.query(Payment).delete()
        self.first = Payment(order_id=91, user_id=42, amount=12.30, method="card", status="REJECTED")
        self.db.add(self.first)
        self.db.flush()
        self.last = Payment(order_id=91, user_id=42, amount=12.30, method="card", status="PAID")
        self.db.add(self.last)
        self.db.commit()

    def test_latest_is_numeric_attempt_order_and_does_not_mutate(self):
        self.assertEqual(get_latest_order_payment(91, {"id": 42}, self.db).id, self.last.id)
        self.assertEqual(self.db.query(Payment).count(), 2)

    def test_other_owner_has_same_404_as_missing_order(self):
        for order, owner in [(91, 99), (99999, 42)]:
            with self.assertRaises(HTTPException) as caught:
                get_latest_order_payment(order, {"id": owner}, self.db)
            self.assertEqual(caught.exception.status_code, 404)

    def test_pending_latest_is_returned_without_recovery_side_effects(self):
        self.last.status = "PENDING"
        self.db.commit()
        result = get_latest_order_payment(91, {"id": 42}, self.db)
        self.assertEqual((result.id, result.status, result.processed_at), (self.last.id, "PENDING", None))


if __name__ == "__main__":
    unittest.main(verbosity=2)

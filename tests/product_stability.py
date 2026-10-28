import concurrent.futures
import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, engine as production_engine
from app.models import Product, ProcessedPaymentEvent, InventoryReservation, InventoryCancellation
from app import rabbitmq
from app.routers.products import decrease_product_stock
from app.schemas import StockDecrease
from app.services import payment_validation
from app.reservations import reserve, release, StockUnavailable, ReservationConflict


class ProductStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_stability_" + uuid.uuid4().hex
        with production_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.engine = create_engine(production_engine.url, connect_args={
            "options": f"-csearch_path={cls.schema}",
        })
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with production_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))

    def setUp(self):
        with self.engine.begin() as conn:
            conn.execute(InventoryCancellation.__table__.delete())
            conn.execute(InventoryReservation.__table__.delete())
            conn.execute(ProcessedPaymentEvent.__table__.delete())
            conn.execute(Product.__table__.delete())
        with self.sessions() as db:
            db.add(Product(id=31, name="Test product", price=10, stock=3))
            db.commit()
        self.message = {
            "event": "PAYMENT_COMPLETED", "order_id": 91,
            "transaction_id": "TX-TEST", "items": [{"product_id": 31, "quantity": 2}],
        }

    def test_concurrent_events_decrease_stock_once(self):
        with patch.object(rabbitmq, "SessionLocal", self.sessions), patch.object(
            rabbitmq, "verify_payment_and_order", return_value=(True, "verified")
        ):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(rabbitmq.process_payment_completed, [self.message, self.message]))
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 31).stock, 1)
            self.assertEqual(db.query(ProcessedPaymentEvent).count(), 1)

    def test_insufficient_stock_rolls_back_entire_event(self):
        self.message["items"].append({"product_id": 32, "quantity": 1})
        with patch.object(rabbitmq, "SessionLocal", self.sessions), patch.object(
            rabbitmq, "verify_payment_and_order", return_value=(True, "verified")
        ):
            with self.assertRaises(ValueError):
                rabbitmq.process_payment_completed(self.message)
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 31).stock, 3)
            self.assertEqual(db.query(ProcessedPaymentEvent).count(), 0)

    def test_concurrent_manual_decrements_cannot_oversell(self):
        def decrease(_):
            with self.sessions() as db:
                try:
                    decrease_product_stock(31, StockDecrease(quantity=2), db, {"role": "admin"})
                    return 200
                except HTTPException as exc:
                    return exc.status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decrease, range(2)))
        self.assertEqual(sorted(results), [200, 400])
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 31).stock, 1)

    def test_order_validation_accepts_event_before_order_consumer(self):
        for state in ("PENDING", "CANCELLING", "PAID", "PROCESSING", "SHIPPED", "DELIVERED"):
            with self.subTest(state=state), patch.object(payment_validation, "internal_get", return_value=(True, {
                "order_id": 91, "user_id": 42, "status": state,
                "items": self.message["items"],
            })):
                self.assertTrue(payment_validation.verify_order(91, self.message["items"])[0])

    def test_cancelled_order_is_rejected(self):
        with patch.object(payment_validation, "internal_get", return_value=(True, {
            "order_id": 91, "user_id": 42, "status": "CANCELLED", "items": self.message["items"],
        })):
            self.assertFalse(payment_validation.verify_order(91, self.message["items"])[0])

    def test_competing_orders_cannot_reserve_same_units(self):
        def attempt(order_id):
            with self.sessions() as db:
                try:
                    reserve(db, f"TX-{order_id}", order_id, 42, self.message["items"])
                    db.commit()
                    return "reserved"
                except StockUnavailable:
                    db.rollback()
                    return "rejected"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [91, 92]))
        self.assertEqual(sorted(results), ["rejected", "reserved"])
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 31).stock, 1)
            self.assertEqual(db.query(InventoryReservation).count(), 1)

    def test_reservation_lost_http_response_reuses_units(self):
        with self.sessions() as db:
            reserve(db, "TX-TEST", 91, 42, self.message["items"])
            db.commit()
        with self.sessions() as db:
            reserve(db, "TX-TEST", 91, 42, self.message["items"])
            db.commit()
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 31).stock, 1)
            self.assertEqual(db.query(InventoryReservation).count(), 1)

    def test_one_missing_item_rolls_back_all_reservations(self):
        with self.sessions() as db:
            with self.assertRaises(StockUnavailable):
                reserve(db, "TX-TEST", 91, 42, self.message["items"] + [{"product_id": 32, "quantity": 1}])
            db.rollback()
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 31).stock, 3)
            self.assertEqual(db.query(InventoryReservation).count(), 0)

    def test_reserved_payment_event_does_not_decrease_again(self):
        with self.sessions() as db:
            reserve(db, "TX-TEST", 91, 42, self.message["items"])
            db.commit()
        self.message.update(user_id=42, inventory_reservation_id="TX-TEST")
        with patch.object(rabbitmq, "SessionLocal", self.sessions), patch.object(
            rabbitmq, "verify_payment_and_order", return_value=(True, "verified")
        ):
            rabbitmq.process_payment_completed(self.message)
            rabbitmq.process_payment_completed(self.message)
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 31).stock, 1)
            self.assertEqual(db.get(InventoryReservation, "TX-TEST").status, "CONSUMED")
            self.assertEqual(db.query(ProcessedPaymentEvent).count(), 1)

    def test_conflicting_reservation_cannot_change_held_units(self):
        with self.sessions() as db:
            reserve(db, "TX-TEST", 91, 42, self.message["items"])
            db.commit()
        with self.sessions() as db:
            with self.assertRaises(ReservationConflict):
                reserve(db, "TX-OTHER", 91, 42, self.message["items"])
            db.rollback()
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 31).stock, 1)

    def test_new_event_cannot_omit_authoritative_reservation(self):
        with patch.object(payment_validation, "verify_payment", return_value=(True, {
            "user_id": 42, "inventory_reservation_id": "TX-TEST",
        })):
            self.assertFalse(payment_validation.verify_payment_and_order(self.message)[0])

    def test_release_restores_units_exactly_once(self):
        with self.sessions() as db:
            reserve(db,"TX-TEST",91,42,self.message["items"])
            db.commit()
            release(db,91)
            db.commit()
            release(db,91)
            db.commit()
            self.assertEqual(db.get(Product,31).stock,3)
            self.assertEqual(db.get(InventoryReservation,"TX-TEST").status,"RELEASED")

    def test_release_without_reservation_blocks_late_reserve(self):
        with self.sessions() as db:
            release(db,91)
            db.commit()
            with self.assertRaises(ReservationConflict):
                reserve(db,"TX-LATE",91,42,self.message["items"])
            db.rollback()
            self.assertEqual(db.get(Product,31).stock,3)

    def test_consumed_reservation_cannot_be_released(self):
        with self.sessions() as db:
            reservation=reserve(db,"TX-TEST",91,42,self.message["items"])
            reservation.status="CONSUMED"
            db.commit()
            with self.assertRaises(ReservationConflict):
                release(db,91)
            db.rollback()
            self.assertEqual(db.get(Product,31).stock,1)

    def test_concurrent_releases_do_not_duplicate_units(self):
        with self.sessions() as db:
            reserve(db,"TX-TEST",91,42,self.message["items"])
            db.commit()
        def attempt(_):
            with self.sessions() as db:
                release(db,91)
                db.commit()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(attempt,range(2)))
        with self.sessions() as db:
            self.assertEqual(db.get(Product,31).stock,3)

    def test_late_reserve_races_with_release_safely(self):
        def attempt(action):
            with self.sessions() as db:
                try:
                    if action=="reserve":
                        reserve(db,"TX-TEST",91,42,self.message["items"])
                    else:
                        release(db,91)
                    db.commit()
                except ReservationConflict:
                    db.rollback()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(attempt,["reserve","release"]))
        with self.sessions() as db:
            self.assertEqual(db.get(Product,31).stock,3)
            self.assertIsNotNone(db.get(InventoryCancellation,91))

    def test_product_with_active_reservation_cannot_be_deleted(self):
        from app.crud.product import delete_product
        with self.sessions() as db:
            reserve(db,"TX-TEST",91,42,self.message["items"])
            db.commit()
            with self.assertRaises(HTTPException) as error:
                delete_product(db,db.get(Product,31))
            self.assertEqual(error.exception.status_code,409)


if __name__ == "__main__":
    unittest.main(verbosity=2)

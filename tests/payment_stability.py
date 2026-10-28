"""Ejecutar dentro de payment-service. Usa un esquema PostgreSQL desechable."""
import concurrent.futures
import unittest
import uuid
from decimal import Decimal
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, engine as production_engine
from app.models import Payment, OutboxEvent, OrderCancellation
from app.routers.payments import create_payment
from app.schemas import PaymentCreate
from app import outbox, inventory
from app.core.rabbitmq import publish_event
from app import cancellations


class PaymentStability(unittest.TestCase):
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
            conn.execute(OrderCancellation.__table__.delete())
            conn.execute(OutboxEvent.__table__.delete())
            conn.execute(Payment.__table__.delete())
        self.order = {
            "id": 91, "user_id": 42, "status": "PENDING", "total": "12.30",
            "items": [{"product_id": 31, "quantity": 2}],
        }
        self.response = Mock(status_code=200)
        self.response.json.return_value = self.order
        self.user = {"id": 42, "token": "test", "email": "test@example.com"}
        reservation = patch.object(inventory, "reserve_stock")
        self.real_reserve_stock = inventory.reserve_stock
        self.reserve_stock = reservation.start()
        self.addCleanup(reservation.stop)

    def pay(self):
        with self.sessions() as db:
            return create_payment(PaymentCreate(order_id=91, method="card"), self.user, db)

    def test_payment_and_three_deliveries_commit_together(self):
        with patch("app.routers.payments.httpx.get", return_value=self.response):
            self.pay()
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).one().amount, Decimal("12.30"))
            events = db.query(OutboxEvent).all()
            self.assertEqual(len(events), 3)
            self.assertEqual(len({e.destination for e in events}), 3)
            self.assertTrue(all(e.status == "PENDING" for e in events))
            self.assertTrue(all(e.payload["amount"] == "12.30" for e in events))

    def test_outbox_insert_failure_rolls_back_payment(self):
        from sqlalchemy import event
        def fail(*args):
            raise RuntimeError("outbox unavailable")
        event.listen(OutboxEvent, "before_insert", fail)
        try:
            with patch("app.routers.payments.httpx.get", return_value=self.response):
                with self.assertRaises(RuntimeError):
                    self.pay()
        finally:
            event.remove(OutboxEvent, "before_insert", fail)
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).count(), 1)
            payment = db.query(Payment).one()
            self.assertEqual(payment.status, "PENDING")
            payment_id = payment.id
            self.assertEqual(db.query(OutboxEvent).count(), 0)
        # El fallo de commit no pierde el intento ni crea un segundo pago.
        with self.sessions() as db:
            inventory.settle_payment(db, payment_id)
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).one().status, "PAID")
            self.assertEqual(db.query(OutboxEvent).count(), 3)

    def test_simultaneous_payments_only_create_one_payment(self):
        def attempt(_):
            try:
                self.pay()
                return 201
            except HTTPException as exc:
                return exc.status_code
        with patch("app.routers.payments.httpx.get", return_value=self.response):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(attempt, range(4)))
        self.assertGreaterEqual(results.count(201), 1)
        self.assertTrue(all(result in (201, 400) for result in results))
        self.reserve_stock.assert_called_once()
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).count(), 1)
            self.assertEqual(db.query(OutboxEvent).count(), 3)

    def test_partial_broker_failure_retries_only_pending_destination(self):
        with patch("app.routers.payments.httpx.get", return_value=self.response):
            self.pay()
        def publish(destination, *_):
            if destination == "product_payment_completed":
                raise ConnectionError("broker unavailable")
        with patch.object(outbox, "SessionLocal", self.sessions):
            with patch.object(outbox, "publish_event", side_effect=publish):
                outbox.dispatch_pending()
            with self.sessions() as db:
                self.assertEqual(db.query(OutboxEvent).filter_by(status="PUBLISHED").count(), 2)
                failed = db.query(OutboxEvent).filter_by(status="PENDING").one()
                self.assertEqual(failed.attempts, 1)
                self.assertIn("broker unavailable", failed.last_error)
            with patch.object(outbox, "publish_event") as publisher:
                outbox.dispatch_pending()
                self.assertEqual(publisher.call_count, 1)
                self.assertEqual(publisher.call_args.args[0], "product_payment_completed")
            with self.sessions() as db:
                self.assertEqual(db.query(OutboxEvent).filter_by(status="PUBLISHED").count(), 3)

    def test_wrong_owner_cannot_pay(self):
        self.order["user_id"] = 99
        with patch("app.routers.payments.httpx.get", return_value=self.response):
            with self.assertRaises(HTTPException) as caught:
                self.pay()
        self.assertEqual(caught.exception.status_code, 403)

    def test_publisher_accepts_blocking_channel_ack_returning_none(self):
        connection = Mock()
        channel = connection.channel.return_value
        channel.basic_publish.return_value = None
        with patch("app.core.rabbitmq.pika.BlockingConnection", return_value=connection):
            publish_event("product_payment_completed", {"event": "PAYMENT_COMPLETED"}, "event-1")
        channel.confirm_delivery.assert_called_once()
        self.assertTrue(channel.basic_publish.call_args.kwargs["mandatory"])
        connection.close.assert_called_once()

    def test_publisher_propagates_broker_nack(self):
        import pika
        connection = Mock()
        connection.channel.return_value.basic_publish.side_effect = pika.exceptions.NackError([])
        with patch("app.core.rabbitmq.pika.BlockingConnection", return_value=connection):
            with self.assertRaises(pika.exceptions.NackError):
                publish_event("product_payment_completed", {}, "event-1")
        connection.close.assert_called_once()

    def test_insufficient_stock_rejects_without_paid_event(self):
        self.reserve_stock.side_effect = inventory.StockUnavailable("sold out")
        with patch("app.routers.payments.httpx.get", return_value=self.response):
            with self.assertRaises(HTTPException) as caught:
                self.pay()
        self.assertEqual(caught.exception.status_code, 409)
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).one().status, "REJECTED")
            self.assertEqual(db.query(OutboxEvent).count(), 0)

    def test_inventory_outage_leaves_recoverable_intent(self):
        self.reserve_stock.side_effect = inventory.InventoryUnavailable("offline")
        with patch("app.routers.payments.httpx.get", return_value=self.response):
            payment = self.pay()
        self.assertEqual(payment.status, "PENDING")
        with self.sessions() as db:
            self.assertEqual(db.query(OutboxEvent).count(), 0)
        self.reserve_stock.side_effect = None
        with patch.object(inventory, "SessionLocal", self.sessions):
            inventory.recover_pending()
            inventory.recover_pending()
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).count(), 1)
            self.assertEqual(db.query(Payment).one().status, "PAID")
            self.assertEqual(db.query(OutboxEvent).count(), 3)

    def test_pending_retry_reuses_same_transaction(self):
        self.reserve_stock.side_effect = inventory.InventoryUnavailable("lost response")
        with patch("app.routers.payments.httpx.get", return_value=self.response):
            first = self.pay()
            self.reserve_stock.side_effect = None
            second = self.pay()
        self.assertEqual(first.transaction_id, second.transaction_id)
        self.assertEqual(second.status, "PAID")
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).count(), 1)
            self.assertEqual(db.query(OutboxEvent).count(), 3)

    def test_pending_http_response_is_accepted(self):
        from fastapi import Response
        self.reserve_stock.side_effect = inventory.InventoryUnavailable("offline")
        response = Response()
        with patch("app.routers.payments.httpx.get", return_value=self.response):
            with self.sessions() as db:
                payment = create_payment(PaymentCreate(order_id=91, method="card"), self.user, db, response)
                self.assertEqual(payment.status, "PENDING")
        self.assertEqual(response.status_code, 202)

    def test_rejected_order_can_retry_after_restocking(self):
        self.reserve_stock.side_effect = inventory.StockUnavailable("sold out")
        with patch("app.routers.payments.httpx.get", return_value=self.response):
            with self.assertRaises(HTTPException):
                self.pay()
            self.reserve_stock.side_effect = None
            self.assertEqual(self.pay().status, "PAID")
        with self.sessions() as db:
            self.assertEqual(sorted(p.status for p in db.query(Payment)), ["PAID", "REJECTED"])
            self.assertEqual(db.query(OutboxEvent).count(), 3)

    def test_stock_client_does_not_reject_on_ambiguous_conflict(self):
        from types import SimpleNamespace
        response = Mock(status_code=409)
        response.json.return_value = {"detail": {"code": "RESERVATION_CONFLICT"}}
        with patch.object(inventory.httpx, "post", return_value=response):
            with self.assertRaises(inventory.InventoryUnavailable):
                self.real_reserve_stock(SimpleNamespace(transaction_id="TX-TEST"))

    def test_stock_client_only_rejects_explicit_stock_shortage(self):
        from types import SimpleNamespace
        response = Mock(status_code=409)
        response.json.return_value = {"detail": {"code": "INSUFFICIENT_STOCK"}}
        with patch.object(inventory.httpx, "post", return_value=response):
            with self.assertRaises(inventory.StockUnavailable):
                self.real_reserve_stock(SimpleNamespace(transaction_id="TX-TEST"))

    def test_stock_client_timeout_does_not_confirm_or_reject(self):
        import httpx
        from types import SimpleNamespace
        with patch.object(inventory.httpx, "post", side_effect=httpx.ReadTimeout("lost response")):
            with self.assertRaises(inventory.InventoryUnavailable):
                self.real_reserve_stock(SimpleNamespace(transaction_id="TX-TEST"))

    def test_cancellation_blocks_stale_create_request(self):
        with self.sessions() as db:
            cancellations.begin_cancellation(db,91,42)
        with patch("app.routers.payments.httpx.get",return_value=self.response):
            with self.assertRaises(HTTPException) as error:
                self.pay()
            self.assertEqual(error.exception.status_code,409)
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).count(),0)

    def test_cancellation_stops_pending_recovery(self):
        self.reserve_stock.side_effect=inventory.InventoryUnavailable("offline")
        with patch("app.routers.payments.httpx.get",return_value=self.response):
            payment=self.pay()
        self.reserve_stock.reset_mock()
        with self.sessions() as db:
            cancellations.begin_cancellation(db,91,42)
            result=inventory.settle_payment(db,payment.id)
            self.assertEqual(result.status,"CANCELLED")
        self.reserve_stock.assert_not_called()

    def test_paid_payment_prevents_cancellation_barrier(self):
        with patch("app.routers.payments.httpx.get",return_value=self.response):
            self.pay()
        with self.sessions() as db:
            with self.assertRaises(HTTPException) as error:
                cancellations.begin_cancellation(db,91,42)
            self.assertEqual(error.exception.status_code,409)
            db.rollback()
            self.assertIsNone(db.get(OrderCancellation,91))

    def test_release_outage_is_retried_and_done_is_idempotent(self):
        import httpx
        with self.sessions() as db:
            cancellations.begin_cancellation(db,91,42)
            with patch.object(cancellations.httpx,"post",side_effect=httpx.ReadTimeout("offline")):
                self.assertEqual(cancellations.finish_cancellation(db,91).status,"PENDING")
        response=Mock(status_code=200)
        response.json.return_value={"order_id":91,"status":"RELEASED"}
        with patch.object(cancellations,"SessionLocal",self.sessions),patch.object(cancellations.httpx,"post",return_value=response) as remote:
            cancellations.recover_cancellations()
            cancellations.recover_cancellations()
            remote.assert_called_once()
        with self.sessions() as db:
            self.assertEqual(db.get(OrderCancellation,91).status,"DONE")

    def test_payment_confirmation_and_cancellation_cannot_both_win(self):
        self.reserve_stock.side_effect=inventory.InventoryUnavailable("offline")
        with patch("app.routers.payments.httpx.get",return_value=self.response):
            payment=self.pay()
        self.reserve_stock.side_effect=None
        def attempt(action):
            with self.sessions() as db:
                try:
                    if action=="pay":
                        inventory.settle_payment(db,payment.id)
                    else:
                        cancellations.begin_cancellation(db,91,42)
                except HTTPException as exc:
                    self.assertEqual(exc.status_code,409)
                    db.rollback()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(attempt,["pay","cancel"]))
        with self.sessions() as db:
            state=db.get(Payment,payment.id).status
            barrier=db.get(OrderCancellation,91)
            self.assertIn(state,("PAID","CANCELLED"))
            self.assertEqual(barrier is not None,state=="CANCELLED")
            self.assertEqual(db.query(OutboxEvent).count(),3 if state=="PAID" else 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

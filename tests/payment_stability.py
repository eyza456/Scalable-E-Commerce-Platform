"""Ejecutar dentro de payment-service. Usa un esquema PostgreSQL desechable."""
import concurrent.futures
import unittest
import uuid
import threading
from contextlib import contextmanager
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
from app.core.rabbitmq import publish_event, publisher_batch
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

    @contextmanager
    def mock_publisher(self, side_effect=None):
        send = Mock(side_effect=side_effect)
        with patch.object(outbox, "publisher_batch") as factory:
            factory.return_value.__enter__.return_value = send
            yield send

    def pay(self):
        with self.sessions() as db:
            return create_payment(PaymentCreate(order_id=91, method="card"), self.user, db)

    def simulated_pay(self, result):
        with self.sessions() as db:
            return create_payment(PaymentCreate(order_id=91, method="card", simulation_result=result), self.user, db)

    def test_simulated_rejections_are_durable_without_stock_or_events(self):
        for result, code in inventory.SIMULATED_REJECTIONS.items():
            with self.subTest(result=result):
                with patch("app.routers.payments.http_client.get", return_value=self.response):
                    with self.assertRaises(HTTPException) as caught:
                        self.simulated_pay(result)
                self.assertEqual(caught.exception.status_code, 409)
                self.assertEqual(caught.exception.detail["code"], code)
                with self.sessions() as db:
                    p = db.query(Payment).filter_by(transaction_id=caught.exception.detail["transaction_id"]).one()
                    self.assertEqual((p.status, p.rejection_code), ("REJECTED", code))
                    self.assertIsNotNone(p.processed_at)
                    stamp = p.processed_at
                    inventory.settle_payment(db, p.id)
                    self.assertEqual(p.processed_at, stamp)
                    self.assertEqual(db.query(OutboxEvent).count(), 0)
        self.reserve_stock.assert_not_called()

    def test_rejected_authorization_allows_later_successful_attempt(self):
        with patch("app.routers.payments.http_client.get", return_value=self.response):
            with self.assertRaises(HTTPException):
                self.simulated_pay("insufficient_funds")
            self.pay()
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).filter_by(status="REJECTED").count(), 1)
            paid = db.query(Payment).filter_by(status="PAID").one()
            self.assertIsNone(paid.rejection_code)
            self.assertEqual(db.query(OutboxEvent).count(), 3)
        self.reserve_stock.assert_called_once()

    def test_recovery_preserves_simulated_rejection_after_process_loss(self):
        with patch("app.routers.payments.http_client.get", return_value=self.response), patch(
                "app.routers.payments.settle_payment", side_effect=RuntimeError("process lost")):
            with self.assertRaises(RuntimeError):
                self.simulated_pay("expired_card")
        with self.sessions() as db:
            p = db.query(Payment).one()
            self.assertEqual((p.status, p.simulation_result), ("PENDING", "expired_card"))
        with patch.object(inventory, "SessionLocal", self.sessions):
            inventory.recover_pending()
            inventory.recover_pending()
        with self.sessions() as db:
            p = db.query(Payment).one()
            self.assertEqual((p.status, p.rejection_code), ("REJECTED", "EXPIRED_CARD"))
            self.assertEqual(db.query(OutboxEvent).count(), 0)
        self.reserve_stock.assert_not_called()

    def test_pending_simulation_cannot_be_overridden(self):
        self.reserve_stock.side_effect = inventory.InventoryUnavailable("offline")
        with patch("app.routers.payments.http_client.get", return_value=self.response):
            self.pay()
            with self.assertRaises(HTTPException) as caught:
                self.simulated_pay("card_declined")
        self.assertEqual(caught.exception.status_code, 409)
        with self.sessions() as db:
            p = db.query(Payment).one()
            self.assertEqual((p.status, p.simulation_result), ("PENDING", "approved"))

    def test_unknown_simulation_is_validation_error(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            PaymentCreate(order_id=91, method="card", simulation_result="random")

    def test_cancellation_takes_priority_over_simulated_rejection(self):
        with patch("app.routers.payments.http_client.get", return_value=self.response), patch(
                "app.routers.payments.settle_payment", side_effect=RuntimeError("process lost")):
            with self.assertRaises(RuntimeError):
                self.simulated_pay("card_declined")
        with self.sessions() as db:
            cancellations.begin_cancellation(db, 91, 42)
            p = db.query(Payment).one()
            inventory.settle_payment(db, p.id)
            self.assertEqual(p.status, "CANCELLED")
            self.assertIsNone(p.rejection_code)
            self.assertEqual(db.query(OutboxEvent).count(), 0)
        self.reserve_stock.assert_not_called()

    def test_payment_and_three_deliveries_commit_together(self):
        with patch("app.routers.payments.http_client.get", return_value=self.response):
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
            with patch("app.routers.payments.http_client.get", return_value=self.response):
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
        with patch("app.routers.payments.http_client.get", return_value=self.response):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(attempt, range(4)))
        self.assertGreaterEqual(results.count(201), 1)
        self.assertTrue(all(result in (201, 400) for result in results))
        self.reserve_stock.assert_called_once()
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).count(), 1)
            self.assertEqual(db.query(OutboxEvent).count(), 3)

    def test_partial_broker_failure_retries_only_pending_destination(self):
        with patch("app.routers.payments.http_client.get", return_value=self.response):
            self.pay()
        def publish(destination, *_):
            if destination == "product_payment_completed":
                raise ConnectionError("broker unavailable")
        with patch.object(outbox, "SessionLocal", self.sessions):
            with self.mock_publisher(side_effect=publish):
                outbox.dispatch_pending()
            with self.sessions() as db:
                self.assertEqual(db.query(OutboxEvent).filter_by(status="PUBLISHED").count(), 2)
                failed = db.query(OutboxEvent).filter_by(status="PENDING").one()
                self.assertEqual(failed.attempts, 1)
                self.assertIn("broker unavailable", failed.last_error)
            with self.mock_publisher() as publisher:
                outbox.dispatch_pending()
                self.assertEqual(publisher.call_count, 1)
                self.assertEqual(publisher.call_args.args[0], "product_payment_completed")
            with self.sessions() as db:
                self.assertEqual(db.query(OutboxEvent).filter_by(status="PUBLISHED").count(), 3)

    def seed_deliveries(self, count):
        with self.sessions() as db:
            for i in range(count):
                db.add(OutboxEvent(event_type="PAYMENT_COMPLETED", aggregate_id=91,
                    destination=("payment_completed", "order_payment_completed", "product_payment_completed")[i % 3],
                    payload={"transaction_id": "TX-OUTBOX-TEST"}))
            db.commit()

    def stop_after_first_wait(self, observations):
        stop = threading.Event()
        def wait(seconds):
            with self.sessions() as db:
                observations.append({"seconds": seconds,
                    "pending": db.query(OutboxEvent).filter_by(status="PENDING").count()})
            stop.set()
            return True
        stop.wait = wait
        return stop

    def test_outbox_drains_multiple_batches_before_waiting(self):
        self.seed_deliveries(120)
        waits = []
        with patch.object(outbox, "SessionLocal", self.sessions), self.mock_publisher() as publish:
            outbox.run_outbox(self.stop_after_first_wait(waits))
        self.assertEqual(publish.call_count, 120)
        self.assertEqual(waits, [{"seconds": 1, "pending": 0}])
        with self.sessions() as db:
            self.assertTrue(all(e.status == "PUBLISHED" and e.attempts == 1 for e in db.query(OutboxEvent)))

    def test_outbox_partial_failure_backs_off_then_retries_only_unpublished(self):
        self.seed_deliveries(60)
        waits, delivered = [], []
        def publish(destination, payload, event_id):
            if destination == "product_payment_completed":
                raise ConnectionError("destination offline")
            delivered.append(event_id)
        with patch.object(outbox, "SessionLocal", self.sessions), self.mock_publisher(side_effect=publish):
            outbox.run_outbox(self.stop_after_first_wait(waits))
        self.assertEqual(len(waits), 1)
        self.assertGreater(waits[0]["pending"], 0)
        self.assertEqual(waits[0]["seconds"], 5)
        with patch.object(outbox, "SessionLocal", self.sessions), self.mock_publisher() as publish:
            outbox.run_outbox(self.stop_after_first_wait([]))
            self.assertEqual(publish.call_count, 60 - len(delivered))
            self.assertTrue(set(delivered).isdisjoint(call.args[2] for call in publish.call_args_list))
        with self.sessions() as db:
            self.assertEqual(db.query(OutboxEvent).filter_by(status="PUBLISHED").count(), 60)

    def test_outbox_database_failure_waits_instead_of_spinning(self):
        waits = []
        with patch.object(outbox, "SessionLocal", side_effect=RuntimeError("db offline")) as factory:
            outbox.run_outbox(self.stop_after_first_wait(waits))
        factory.assert_called_once()
        self.assertEqual(waits, [{"seconds": 5, "pending": 0}])

    def test_outbox_workers_skip_locked_without_duplicate_delivery(self):
        self.seed_deliveries(100)
        barrier, local = threading.Barrier(2), threading.local()
        def publish(*args):
            if not getattr(local, "started", False):
                local.started = True
                barrier.wait(timeout=10)
        with patch.object(outbox, "SessionLocal", self.sessions), self.mock_publisher(side_effect=publish) as publisher:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: outbox.dispatch_pending(), range(2)))
            self.assertEqual(sum(r.published for r in results), 100)
            self.assertEqual(len({call.args[2] for call in publisher.call_args_list}), 100)
        with self.sessions() as db:
            self.assertTrue(all(e.status == "PUBLISHED" and e.attempts == 1 for e in db.query(OutboxEvent)))

    def test_outbox_commit_failure_keeps_delivery_recoverable(self):
        from sqlalchemy import event
        self.seed_deliveries(1)
        def fail(session):
            raise RuntimeError("commit lost")
        with patch.object(outbox, "SessionLocal", self.sessions), self.mock_publisher() as publish:
            event.listen(self.sessions.class_, "before_commit", fail)
            try:
                with self.assertRaises(RuntimeError):
                    outbox.dispatch_pending()
            finally:
                event.remove(self.sessions.class_, "before_commit", fail)
            with self.sessions() as db:
                row = db.query(OutboxEvent).one()
                self.assertEqual((row.status, row.attempts), ("PENDING", 0))
            self.assertEqual(outbox.dispatch_pending().published, 1)
            self.assertEqual(publish.call_count, 2)
            self.assertEqual(publish.call_args_list[0].args[2], publish.call_args_list[1].args[2])

    def test_wrong_owner_cannot_pay(self):
        self.order["user_id"] = 99
        with patch("app.routers.payments.http_client.get", return_value=self.response):
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

    def test_publisher_batch_reuses_channel_but_confirms_each_message(self):
        connection = Mock()
        channel = connection.channel.return_value
        channel.basic_publish.return_value = None
        with patch("app.core.rabbitmq.pika.BlockingConnection", return_value=connection) as factory:
            with publisher_batch() as send:
                send("payment_completed", {"n": 1}, "event-1")
                send("payment_completed", {"n": 2}, "event-2")
                send("order_payment_completed", {"n": 3}, "event-3")
        factory.assert_called_once()
        channel.confirm_delivery.assert_called_once()
        self.assertEqual(channel.queue_declare.call_count, 2)
        self.assertEqual(channel.basic_publish.call_count, 3)
        self.assertEqual([c.kwargs["properties"].message_id for c in channel.basic_publish.call_args_list],
                         ["event-1", "event-2", "event-3"])
        self.assertTrue(all(c.kwargs["mandatory"] and c.kwargs["properties"].delivery_mode == 2
                            for c in channel.basic_publish.call_args_list))
        connection.close.assert_called_once()

    def test_outbox_broker_unavailable_keeps_attempts_and_backoff(self):
        self.seed_deliveries(3)
        waits = []
        with patch.object(outbox, "SessionLocal", self.sessions), patch(
                "app.core.rabbitmq.pika.BlockingConnection", side_effect=ConnectionError("broker offline")) as factory:
            outbox.run_outbox(self.stop_after_first_wait(waits))
        factory.assert_called_once()
        self.assertEqual(waits, [{"seconds": 5, "pending": 3}])
        with self.sessions() as db:
            self.assertTrue(all(e.attempts == 1 and e.status == "PENDING" and "broker offline" in e.last_error
                                for e in db.query(OutboxEvent)))

    def test_outbox_batch_nack_does_not_mark_failed_delivery_published(self):
        import pika
        self.seed_deliveries(3)
        connection = Mock()
        connection.channel.return_value.basic_publish.side_effect = [None, pika.exceptions.NackError([]), None]
        waits = []
        with patch.object(outbox, "SessionLocal", self.sessions), patch(
                "app.core.rabbitmq.pika.BlockingConnection", return_value=connection):
            outbox.run_outbox(self.stop_after_first_wait(waits))
        self.assertEqual(waits, [{"seconds": 5, "pending": 1}])
        with self.sessions() as db:
            self.assertEqual(db.query(OutboxEvent).filter_by(status="PUBLISHED").count(), 2)
        connection.close.assert_called_once()

    def test_publisher_batch_propagates_unroutable_and_closes_connection(self):
        import pika
        connection = Mock()
        connection.channel.return_value.basic_publish.side_effect = pika.exceptions.UnroutableError([])
        with patch("app.core.rabbitmq.pika.BlockingConnection", return_value=connection):
            with self.assertRaises(pika.exceptions.UnroutableError):
                with publisher_batch() as send:
                    send("payment_completed", {}, "event-1")
        connection.close.assert_called_once()

    def test_outbox_empty_queue_does_not_open_broker_connection(self):
        waits = []
        with patch.object(outbox, "SessionLocal", self.sessions), patch(
                "app.core.rabbitmq.pika.BlockingConnection") as factory:
            outbox.run_outbox(self.stop_after_first_wait(waits))
        factory.assert_not_called()
        self.assertEqual(waits, [{"seconds": 1, "pending": 0}])

    def test_insufficient_stock_rejects_without_paid_event(self):
        self.reserve_stock.side_effect = inventory.StockUnavailable("sold out")
        with patch("app.routers.payments.http_client.get", return_value=self.response):
            with self.assertRaises(HTTPException) as caught:
                self.pay()
        self.assertEqual(caught.exception.status_code, 409)
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).one().status, "REJECTED")
            self.assertEqual(db.query(OutboxEvent).count(), 0)

    def test_inventory_outage_leaves_recoverable_intent(self):
        self.reserve_stock.side_effect = inventory.InventoryUnavailable("offline")
        with patch("app.routers.payments.http_client.get", return_value=self.response):
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
        with patch("app.routers.payments.http_client.get", return_value=self.response):
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
        with patch("app.routers.payments.http_client.get", return_value=self.response):
            with self.sessions() as db:
                payment = create_payment(PaymentCreate(order_id=91, method="card"), self.user, db, response)
                self.assertEqual(payment.status, "PENDING")
        self.assertEqual(response.status_code, 202)

    def test_rejected_order_can_retry_after_restocking(self):
        self.reserve_stock.side_effect = inventory.StockUnavailable("sold out")
        with patch("app.routers.payments.http_client.get", return_value=self.response):
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
        with patch.object(inventory.http_client, "post", return_value=response):
            with self.assertRaises(inventory.InventoryUnavailable):
                self.real_reserve_stock(SimpleNamespace(transaction_id="TX-TEST"))

    def test_stock_client_only_rejects_explicit_stock_shortage(self):
        from types import SimpleNamespace
        response = Mock(status_code=409)
        response.json.return_value = {"detail": {"code": "INSUFFICIENT_STOCK"}}
        with patch.object(inventory.http_client, "post", return_value=response):
            with self.assertRaises(inventory.StockUnavailable):
                self.real_reserve_stock(SimpleNamespace(transaction_id="TX-TEST"))

    def test_stock_client_timeout_does_not_confirm_or_reject(self):
        import httpx
        from types import SimpleNamespace
        with patch.object(inventory.http_client, "post", side_effect=httpx.ReadTimeout("lost response")):
            with self.assertRaises(inventory.InventoryUnavailable):
                self.real_reserve_stock(SimpleNamespace(transaction_id="TX-TEST"))

    def test_cancellation_blocks_stale_create_request(self):
        with self.sessions() as db:
            cancellations.begin_cancellation(db,91,42)
        with patch("app.routers.payments.http_client.get",return_value=self.response):
            with self.assertRaises(HTTPException) as error:
                self.pay()
            self.assertEqual(error.exception.status_code,409)
        with self.sessions() as db:
            self.assertEqual(db.query(Payment).count(),0)

    def test_cancellation_stops_pending_recovery(self):
        self.reserve_stock.side_effect=inventory.InventoryUnavailable("offline")
        with patch("app.routers.payments.http_client.get",return_value=self.response):
            payment=self.pay()
        self.reserve_stock.reset_mock()
        with self.sessions() as db:
            cancellations.begin_cancellation(db,91,42)
            result=inventory.settle_payment(db,payment.id)
            self.assertEqual(result.status,"CANCELLED")
        self.reserve_stock.assert_not_called()

    def test_paid_payment_prevents_cancellation_barrier(self):
        with patch("app.routers.payments.http_client.get",return_value=self.response):
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
            with patch.object(cancellations.http_client,"post",side_effect=httpx.ReadTimeout("offline")):
                self.assertEqual(cancellations.finish_cancellation(db,91).status,"PENDING")
        response=Mock(status_code=200)
        response.json.return_value={"order_id":91,"status":"RELEASED"}
        with patch.object(cancellations,"SessionLocal",self.sessions),patch.object(cancellations.http_client,"post",return_value=response) as remote:
            cancellations.recover_cancellations()
            cancellations.recover_cancellations()
            remote.assert_called_once()
        with self.sessions() as db:
            self.assertEqual(db.get(OrderCancellation,91).status,"DONE")

    def test_payment_confirmation_and_cancellation_cannot_both_win(self):
        self.reserve_stock.side_effect=inventory.InventoryUnavailable("offline")
        with patch("app.routers.payments.http_client.get",return_value=self.response):
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

    def test_terminal_timestamp_is_set_once_after_pending_recovery(self):
        self.reserve_stock.side_effect=inventory.InventoryUnavailable("offline")
        with patch("app.routers.payments.http_client.get",return_value=self.response):
            payment=self.pay()
        self.assertIsNone(payment.processed_at)
        self.reserve_stock.side_effect=None
        with self.sessions() as db:
            resolved=inventory.settle_payment(db,payment.id)
            timestamp=resolved.processed_at
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(timestamp.tzinfo)
            self.assertEqual(inventory.settle_payment(db,payment.id).processed_at,timestamp)

    def test_rejected_payment_has_terminal_timestamp(self):
        self.reserve_stock.side_effect=inventory.StockUnavailable("sold out")
        with patch("app.routers.payments.http_client.get",return_value=self.response),self.assertRaises(HTTPException):
            self.pay()
        with self.sessions() as db:self.assertIsNotNone(db.query(Payment).one().processed_at)

    def test_cancelled_pending_payment_has_terminal_timestamp(self):
        self.reserve_stock.side_effect=inventory.InventoryUnavailable("offline")
        with patch("app.routers.payments.http_client.get",return_value=self.response):self.pay()
        with self.sessions() as db:
            cancellations.begin_cancellation(db,91,42)
            self.assertIsNotNone(db.query(Payment).one().processed_at)


if __name__ == "__main__":
    unittest.main(verbosity=2)

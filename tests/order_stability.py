import unittest
import json
import uuid
from datetime import datetime
from unittest.mock import Mock, patch

import httpx
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, engine as production_engine
from app.models import Order, OrderItem
from app.routers.orders import list_orders, cancel_order
from app import cancellations, rabbitmq


class OrderStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_orders_" + uuid.uuid4().hex
        with production_engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.engine = create_engine(production_engine.url, connect_args={"options":f"-csearch_path={cls.schema}"})
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with production_engine.begin() as c:
            c.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(OrderItem.__table__.delete())
            c.execute(Order.__table__.delete())
        with self.sessions() as db:
            for oid, uid, state in ((91,42,"PENDING"),(92,42,"PENDING"),(93,99,"PENDING"),(94,42,"PAID")):
                db.add(Order(id=oid,user_id=uid,status=state,total=10,created_at=datetime(2026,1,1),items=[
                    OrderItem(product_id=31,product_name="Test",quantity=1,price=10,subtotal=10)]))
            db.commit()
        self.user = {"id":42}
        self.done = Mock(status_code=200)
        self.done.json.return_value = {"order_id":91,"user_id":42,"status":"DONE"}

    def test_history_only_contains_owner_and_stable_order(self):
        with self.sessions() as db:
            rows = json.loads(list_orders(0,20,None,self.user,db).body)
            self.assertEqual([r["id"] for r in rows],[94,92,91])
            self.assertEqual(rows[0]["items"][0]["product_name"],"Test")

    def test_history_status_filter_and_pagination(self):
        with self.sessions() as db:
            self.assertEqual([r["id"] for r in json.loads(list_orders(1,1,"PENDING",self.user,db).body)],[91])

    def test_history_empty_for_other_account(self):
        with self.sessions() as db:
            self.assertEqual(json.loads(list_orders(0,20,None,{"id":100},db).body),[])

    def test_history_releases_read_connection_and_preserves_response_schema(self):
        with self.sessions() as db:
            response = list_orders(0,20,None,self.user,db)
            self.assertFalse(db.in_transaction())
        rows = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(rows[0]), {"id", "user_id", "status", "total", "created_at", "items", "checkout_id"})
        self.assertEqual(rows[0]["total"], "10.00")
        self.assertEqual(rows[0]["items"][0]["price"], "10.00")
        self.assertTrue(all(r["user_id"] == 42 for r in rows))

    def test_cannot_cancel_other_users_order(self):
        with self.sessions() as db:
            with self.assertRaises(HTTPException) as error:
                cancel_order(93,Response(),self.user,db)
            self.assertEqual(error.exception.status_code,404)

    def test_confirmed_payment_is_not_cancelable(self):
        with self.sessions() as db:
            with self.assertRaises(HTTPException) as error:
                cancel_order(94,Response(),self.user,db)
            self.assertEqual(error.exception.status_code,409)
            self.assertEqual(db.get(Order,94).status,"PAID")

    def test_successful_cancellation_is_idempotent(self):
        with self.sessions() as db,patch.object(cancellations.http_client,"post",return_value=self.done) as remote:
            self.assertEqual(cancel_order(91,Response(),self.user,db).status,"CANCELLED")
            self.assertEqual(cancel_order(91,Response(),self.user,db).status,"CANCELLED")
            remote.assert_called_once()

    def test_outage_is_durable_and_automatically_recovered(self):
        response = Response()
        with self.sessions() as db,patch.object(cancellations.http_client,"post",side_effect=httpx.ReadTimeout("offline")):
            self.assertEqual(cancel_order(91,response,self.user,db).status,"CANCELLING")
        self.assertEqual(response.status_code,202)
        with patch.object(cancellations,"SessionLocal",self.sessions),patch.object(cancellations.http_client,"post",return_value=self.done):
            cancellations.recover_cancellations()
        with self.sessions() as db:
            self.assertEqual(db.get(Order,91).status,"CANCELLED")

    def test_payment_wins_race_restores_paid_even_without_event(self):
        response = Mock(status_code=409)
        response.json.return_value = {"detail":{"code":"PAYMENT_CONFIRMED","order_id":91}}
        with self.sessions() as db,patch.object(cancellations.http_client,"post",return_value=response):
            with self.assertRaises(HTTPException) as error:
                cancel_order(91,Response(),self.user,db)
            self.assertEqual(error.exception.status_code,409)
            self.assertEqual(db.get(Order,91).status,"PAID")

    def test_wrong_remote_owner_cannot_finalize_cancellation(self):
        self.done.json.return_value["user_id"] = 99
        with self.sessions() as db,patch.object(cancellations.http_client,"post",return_value=self.done):
            self.assertEqual(cancel_order(91,Response(),self.user,db).status,"CANCELLING")

    def test_payment_consumer_waits_for_cancellation_decision(self):
        with self.sessions() as db:
            db.get(Order,91).status = "CANCELLING"
            db.commit()
        with patch.object(rabbitmq,"SessionLocal",self.sessions),patch.object(rabbitmq,"verify_payment_event"):
            with self.assertRaises(rabbitmq.TemporaryValidationError):
                rabbitmq.process_payment_completed({"event":"PAYMENT_COMPLETED","order_id":91})

    def test_advanced_paid_order_cannot_look_like_successful_cancellation(self):
        def concurrent_advance(db, oid):
            order=db.get(Order,oid)
            order.status="PROCESSING"
            db.commit()
            return order
        with self.sessions() as db,patch("app.order_actions.finish_cancellation",side_effect=concurrent_advance):
            with self.assertRaises(HTTPException) as error:
                cancel_order(91,Response(),self.user,db)
            self.assertEqual(error.exception.status_code,409)
            self.assertEqual(db.get(Order,91).status,"PROCESSING")


if __name__ == "__main__":
    unittest.main(verbosity=2)

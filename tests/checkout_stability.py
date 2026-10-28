import concurrent.futures
import copy
from decimal import Decimal
import threading
import unittest
import uuid
from unittest.mock import Mock,patch

from fastapi import HTTPException,Response
from sqlalchemy import create_engine,text,event
from sqlalchemy.orm import sessionmaker

from app.database import Base,engine as production_engine
from app.models import Order,OrderItem,Checkout
from app.routers.orders import create_order,get_checkout
from app import checkouts


class CheckoutStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema="test_checkout_"+uuid.uuid4().hex
        with production_engine.begin() as c:c.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.engine=create_engine(production_engine.url,connect_args={"options":f"-csearch_path={cls.schema}"})
        Base.metadata.create_all(cls.engine)
        cls.sessions=sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with production_engine.begin() as c:c.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(Checkout.__table__.delete());c.execute(OrderItem.__table__.delete());c.execute(Order.__table__.delete())
        self.user={"id":42,"token":"test"}
        self.version=str(uuid.uuid4())
        self.cart={"user_id":42,"version":self.version,"checkout_id":None,"last_checkout_id":None,
                   "items":[{"product_id":31,"name":"Old name","price":"2.00","quantity":2,"subtotal":"999.00"}],"total":"999.00"}
        self.product={"id":31,"name":"Current name","price":"2.00","stock":5,"is_active":True}
        self.product_status=200
        self.prepare_down=self.commit_down=self.abort_down=False
        self.lock=threading.Lock()
        self.patches=[patch.object(checkouts.httpx,"get",side_effect=self.get),
                      patch.object(checkouts.httpx,"post",side_effect=self.post)]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def reply(self,status,data):
        response=Mock(status_code=status);response.json.return_value=copy.deepcopy(data);return response

    def get(self,url,**kwargs):
        if url.endswith("/cart"):
            with self.lock:return self.reply(200,self.cart)
        return self.reply(self.product_status,self.product)

    def post(self,url,**kwargs):
        with self.lock:
            action=url.rsplit("/",1)[-1]
            if action=="prepare":
                if self.prepare_down:return self.reply(503,{})
                self.cart["checkout_id"]=self.version
                return self.reply(200,self.cart)
            if (action=="commit" and self.commit_down) or (action=="abort" and self.abort_down):
                return self.reply(503,{})
            self.cart["checkout_id"]=None
            self.cart["version"]=str(uuid.uuid4())
            self.cart["last_checkout_id"]=self.version if action=="commit" else None
            if action=="commit":self.cart["items"]=[]
            return self.reply(200,{"checkout_id":self.version,"state":"COMMITTED" if action=="commit" else "ABORTED"})

    def create(self,key=None):
        response=Response()
        with self.sessions() as db:
            result=create_order(self.user,db,response,key)
            return result,response.status_code

    def recover(self):
        with patch.object(checkouts,"SessionLocal",self.sessions):checkouts.recover_checkouts()

    def assert_rejected(self,code):
        with self.assertRaises(HTTPException) as error:self.create()
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual(error.exception.detail["code"],code)
        with self.sessions() as db:self.assertEqual(db.query(Order).count(),0)

    def test_revalidates_catalog_and_recomputes_total(self):
        result,status=self.create()
        self.assertEqual(status,201)
        self.assertEqual(result.total,Decimal("4.00"))
        self.assertEqual(result.items[0].product_name,"Current name")

    def test_inactive_product_is_rejected(self):
        self.product["is_active"]=False;self.assert_rejected("PRODUCT_UNAVAILABLE")

    def test_deleted_product_is_rejected(self):
        self.product_status=404;self.assert_rejected("PRODUCT_UNAVAILABLE")

    def test_insufficient_stock_is_rejected(self):
        self.product["stock"]=1;self.assert_rejected("INSUFFICIENT_STOCK")

    def test_changed_price_requires_explicit_reconfirmation(self):
        self.product["price"]="3.00";self.assert_rejected("PRICE_CHANGED")
        self.assertEqual(self.cart["items"][0]["price"],"2.00")
        self.assertIsNone(self.cart["checkout_id"])

    def test_concurrent_checkouts_create_exactly_one_order(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.create()[0].id,range(4)))
        self.assertEqual(len(set(results)),1)
        with self.sessions() as db:
            self.assertEqual(db.query(Order).count(),1);self.assertEqual(db.query(Checkout).count(),1)

    def test_retry_after_lost_response_returns_original_order(self):
        first,_=self.create();self.product["price"]="99.00"
        second,status=self.create(uuid.UUID(self.version))
        self.assertEqual(first.id,second.id);self.assertEqual(status,200)

    def test_cart_finalization_outage_does_not_duplicate_order(self):
        self.commit_down=True
        first,status=self.create();self.assertEqual(status,201)
        with self.sessions() as db:self.assertEqual(db.get(Checkout,self.version).state,"FINALIZING")
        self.commit_down=False;self.recover();self.recover()
        with self.sessions() as db:
            self.assertEqual(db.query(Order).count(),1);self.assertEqual(db.get(Checkout,self.version).state,"COMPLETE")

    def test_catalog_outage_returns_pending_then_recovers(self):
        self.product_status=503
        result,status=self.create();self.assertEqual(status,202);self.assertEqual(result.checkout_id,self.version)
        self.product_status=200;self.recover()
        with self.sessions() as db:self.assertEqual(db.query(Order).count(),1)

    def test_failed_order_commit_reuses_durable_intent(self):
        def fail(*args):raise RuntimeError("database failed")
        event.listen(Order,"before_insert",fail)
        try:
            with self.assertRaises(RuntimeError):self.create()
        finally:event.remove(Order,"before_insert",fail)
        with self.sessions() as db:self.assertEqual(db.get(Checkout,self.version).state,"PENDING")
        self.recover()
        with self.sessions() as db:self.assertEqual(db.query(Order).count(),1)

    def test_abort_outage_is_recovered_without_creating_order(self):
        self.product["stock"]=0;self.abort_down=True
        self.assert_rejected("INSUFFICIENT_STOCK")
        with self.sessions() as db:self.assertEqual(db.get(Checkout,self.version).state,"ABORTING")
        self.abort_down=False;self.recover()
        with self.sessions() as db:
            self.assertEqual(db.query(Order).count(),0);self.assertEqual(db.get(Checkout,self.version).state,"REJECTED")

    def test_checkout_receipt_is_private(self):
        self.create()
        with self.sessions() as db,self.assertRaises(HTTPException) as error:
            get_checkout(uuid.UUID(self.version),Response(),{"id":99},db)
        self.assertEqual(error.exception.status_code,404)

    def test_wrong_cart_version_cannot_create_order(self):
        with self.assertRaises(HTTPException) as error:self.create(uuid.uuid4())
        self.assertEqual(error.exception.status_code,409)


if __name__=="__main__":unittest.main(verbosity=2)

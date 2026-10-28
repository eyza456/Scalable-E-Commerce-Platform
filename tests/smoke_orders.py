import json
import time
import uuid
from urllib.parse import urlencode

from smoke_purchase import request, service_code, wait_for_inventory
from smoke_inventory import cleanup


def main():
    marker="orders-test-"+uuid.uuid4().hex
    user=product=None
    orders=[]
    other=None
    complete=False
    try:
        for suffix in ("owner","other"):
            created=request(8001,"/auth/register","POST",{
                "name":marker+suffix,"email":marker+suffix+"@example.com","password":"Orders-Test-2026",
            },expected=201)
            if suffix=="owner":
                user=created
            else:
                other=created
        token=request(8001,"/auth/login","POST",{"email":user["email"],"password":"Orders-Test-2026"})["access_token"]
        other_token=request(8001,"/auth/login","POST",{"email":other["email"],"password":"Orders-Test-2026"})["access_token"]
        admin=service_code("payment-service",'''
import sys
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({"sub":sys.argv[1],"role":"admin","email":sys.argv[2],
                  "exp":datetime.now(timezone.utc)+timedelta(minutes=3)},
                 settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
''',user["id"],user["email"])
        product=request(8002,"/products/","POST",{"name":marker,"price":"10.00","stock":5},admin,expected=201)
        def make_order():
            request(8003,"/cart/items","POST",{"product_id":product["id"],"quantity":2},token,expected=201)
            order=request(8004,"/orders","POST",token=token,expected=201)
            orders.append(order)
            return order
        pending=make_order()
        request(8004,"/orders",expected=401)
        request(8004,"/orders?limit=101",token=token,expected=422)
        request(8004,"/orders?status=INVALID",token=token,expected=422)
        assert request(8004,"/orders",token=other_token)==[]
        request(8004,f'/orders/{pending["id"]}/cancel',"POST",token=other_token,expected=404)
        request(8004,f'/orders/{pending["id"]}/cancel',"POST",expected=401)
        assert request(8004,f'/orders/{pending["id"]}/cancel',"POST",token=token)["status"]=="CANCELLED"
        assert request(8004,f'/orders/{pending["id"]}/cancel',"POST",token=token)["status"]=="CANCELLED"
        request(8005,"/payments","POST",{"order_id":pending["id"],"method":"card"},token,expected=400)
        assert request(8002,f'/products/{product["id"]}')["stock"]==5

        held=make_order()
        # Mantener el bloqueo de confirmacion mientras se crea una reserva real.
        # La cancelacion publica se encola; al liberar el bloqueo debe ganar ella.
        transaction_id=service_code("payment-service",'''
import json,sys,time,uuid
import httpx
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import engine
from app.models import Payment
from app.inventory import reserve_stock
order=json.loads(sys.argv[1]); tx="TX-CANCEL-"+uuid.uuid4().hex[:12]
with engine.connect() as conn:
    conn.execute(text("SELECT pg_advisory_lock(17001,:id)"),{"id":order["id"]})
    conn.commit()
    try:
        with Session(bind=conn) as db:
            p=Payment(order_id=order["id"],user_id=order["user_id"],amount=order["total"],method="card",status="PENDING",transaction_id=tx,
                event_payload={"event":"PAYMENT_COMPLETED","order_id":order["id"],"user_id":order["user_id"],"email":sys.argv[3],
                    "amount":str(order["total"]),"transaction_id":tx,"inventory_reservation_id":tx,
                    "items":[{"product_id":x["product_id"],"quantity":x["quantity"]} for x in order["items"]]})
            db.add(p); db.commit(); reserve_stock(p); db.rollback()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(httpx.post,f'http://order-service:8000/orders/{order["id"]}/cancel',
                               headers={"Authorization":"Bearer "+sys.argv[2]},timeout=25)
            deadline=time.monotonic()+10
            try:
                while not conn.execute(text("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND classid=17001 AND objid=:id AND NOT granted)"),{"id":order["id"]}).scalar():
                    assert time.monotonic()<deadline,"La cancelacion no alcanzo el bloqueo"
                    time.sleep(0.1)
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(17001,:id)"),{"id":order["id"]}); conn.commit()
            response=future.result()
            assert response.status_code in (200,202),(response.status_code,response.text)
    finally:
        conn.execute(text("SELECT pg_advisory_unlock_all()")); conn.commit()
print(tx)
''',json.dumps(held),token,user["email"])
        deadline=time.monotonic()+35
        while request(8004,f'/orders/{held["id"]}',token=token)["status"]!="CANCELLED":
            assert time.monotonic()<deadline,"Cancelacion no recuperada"
            time.sleep(0.5)
        assert request(8002,f'/products/{product["id"]}')["stock"]==5
        assert request(8005,"/payments/transactions/"+transaction_id,token=token)["status"]=="CANCELLED"
        request(8004,f'/orders/{held["id"]}/cancel',"POST",token=token)
        assert request(8002,f'/products/{product["id"]}')["stock"]==5

        paid=make_order()
        request(8005,"/payments","POST",{"order_id":paid["id"],"method":"card"},token,expected=201)
        wait_for_inventory(paid["id"])
        request(8004,f'/orders/{paid["id"]}/cancel',"POST",token=token,expected=409)
        assert request(8002,f'/products/{product["id"]}')["stock"]==3
        history=request(8004,"/orders?"+urlencode({"status":"CANCELLED","limit":1}),token=token)
        assert [row["id"] for row in history]==[held["id"]]
        assert len(request(8004,"/orders",token=token))==3
        complete=True
        print("OK: historial privado, filtros, cancelacion idempotente, reserva real liberada una vez y pago confirmado protegido.")
    finally:
        if complete or not orders:
            cleanup(user,product,orders)
            cleanup(other,None,[])
        else:
            print("Datos de prueba conservados para diagnostico:",marker)


if __name__=="__main__":
    main()

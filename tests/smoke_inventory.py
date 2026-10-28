"""Carrera de dos compras y recuperacion real tras caer despues de reservar."""
import concurrent.futures
import json
import time
import uuid

from smoke_purchase import request, service_code, wait_for_inventory


def cleanup(user, product, orders):
    # Cada ID proviene de una solicitud creada por esta prueba.
    for order in orders:
        service_code("payment-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as c:
    p={"id":int(sys.argv[1])}
    c.execute(text("DELETE FROM outbox_events WHERE aggregate_id=:id"),p)
    c.execute(text("DELETE FROM order_cancellations WHERE order_id=:id"),p)
    c.execute(text("DELETE FROM payments WHERE order_id=:id"),p)
''', order["id"])
        service_code("order-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as c:
    p={"id":int(sys.argv[1])}
    c.execute(text("DELETE FROM order_items WHERE order_id=:id"),p)
    c.execute(text("DELETE FROM orders WHERE id=:id"),p)
''', order["id"])
        service_code("product-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as c:
    p={"id":int(sys.argv[1])}
    c.execute(text("DELETE FROM processed_payment_events WHERE order_id=:id"),p)
    c.execute(text("DELETE FROM inventory_reservations WHERE order_id=:id"),p)
    c.execute(text("DELETE FROM inventory_cancellations WHERE order_id=:id"),p)
''', order["id"])
    if product:
        service_code("product-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as c:
    c.execute(text("DELETE FROM products WHERE id=:id AND name=:name"),
              {"id":int(sys.argv[1]),"name":sys.argv[2]})
''', product["id"], product["name"])
    if user:
        service_code("order-service", "import sys; from sqlalchemy import text; from app.database import engine; conn=engine.connect(); conn.execute(text('DELETE FROM checkouts WHERE user_id=:id'), {'id':int(sys.argv[1])}); conn.commit(); conn.close()", user["id"])
        service_code("cart-service", '''
import sys
from app.redis_client import redis_client
redis_client.delete("cart:" + sys.argv[1])
''', user["id"])
        service_code("user-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as c:
    c.execute(text("DELETE FROM users WHERE id=:id AND email=:email"),
              {"id":int(sys.argv[1]),"email":sys.argv[2]})
''', user["id"], user["email"])


def wait_for_purchase(order, product, token):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        status = request(8004, f'/orders/{order["id"]}', token=token)["status"]
        stock = request(8002, f'/products/{product["id"]}')["stock"]
        if status == "PAID" and stock == 1:
            wait_for_inventory(order["id"])
            return
        time.sleep(0.5)
    raise AssertionError("No se recupero la compra en 40 segundos")


def main():
    marker = "reservation-test-" + uuid.uuid4().hex
    user = product = None
    orders = []
    complete = False
    try:
        user = request(8001, "/auth/register", "POST", {
            "name": marker, "email": marker + "@example.com", "password": "Test-Reservation-2026",
        }, expected=201)
        token = request(8001, "/auth/login", "POST", {
            "email": user["email"], "password": "Test-Reservation-2026",
        })["access_token"]
        admin = service_code("payment-service", '''
import sys
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({"sub":sys.argv[1],"email":sys.argv[2],"role":"admin",
                  "exp":datetime.now(timezone.utc)+timedelta(minutes=3)},
                 settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
''', user["id"], user["email"])
        product = request(8002, "/products/", "POST", {
            "name": marker, "price": "12.30", "stock": 3,
        }, admin, expected=201)

        def make_order():
            request(8003, "/cart/items", "POST", {"product_id": product["id"], "quantity": 2}, token, expected=201)
            order = request(8004, "/orders", "POST", token=token, expected=201)
            orders.append(order)
            return order

        make_order()
        make_order()

        def pay(order):
            # En este contrato ambas respuestas son validas: una gana y otra pierde stock.
            import urllib.request
            import urllib.error
            req = urllib.request.Request("http://localhost:8005/payments",
                data=json.dumps({"order_id":order["id"],"method":"card"}).encode(),
                headers={"Content-Type":"application/json","Authorization":"Bearer "+token})
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    return order, response.status, json.load(response)
            except urllib.error.HTTPError as exc:
                return order, exc.code, json.load(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(pay, orders))
        assert sorted(status for _, status, _ in results) == [201, 409], results
        winner = next(order for order, status, _ in results if status == 201)
        loser = next(order for order, status, _ in results if status == 409)
        rejection = next(body for _, status, body in results if status == 409)
        assert rejection["detail"]["code"] == "INSUFFICIENT_STOCK", rejection
        wait_for_purchase(winner, product, token)
        assert request(8004, f'/orders/{loser["id"]}', token=token)["status"] == "PENDING"
        rejected = request(8005, "/payments/transactions/" + rejection["detail"]["transaction_id"], token=token)
        assert rejected["status"] == "REJECTED", rejected
        print("OK: dos compras simultaneas, un PAID y un REJECTED; stock disponible=1.")

        # Reponer para una segunda compra independiente que cae tras reservar.
        request(8002, f'/products/{product["id"]}', "PUT", {"stock":3}, admin)
        recovery_order = make_order()
        transaction_id = service_code("payment-service", '''
import json,sys,uuid
from app.database import SessionLocal
from app.models import Payment
from app.inventory import reserve_stock
order=json.loads(sys.argv[1])
tx="TX-CRASH-"+uuid.uuid4().hex[:12]
with SessionLocal() as db:
    payment=Payment(order_id=order["id"], user_id=order["user_id"], amount=order["total"],
                    method="card",status="PENDING",transaction_id=tx,
                    event_payload={"event":"PAYMENT_COMPLETED","order_id":order["id"],
                        "user_id":order["user_id"],"email":sys.argv[2],"amount":str(order["total"]),
                        "transaction_id":tx,"inventory_reservation_id":tx,
                        "items":[{"product_id":x["product_id"],"quantity":x["quantity"]} for x in order["items"]]})
    db.add(payment)
    db.flush()
    pid=payment.id
    db.commit()
    payment=db.query(Payment).filter_by(id=pid).with_for_update().one()
    reserve_stock(payment)
    # Fin del proceso sin confirmar PAID; la reserva remota ya esta persistida.
    print(tx)
''', json.dumps(recovery_order), user["email"])
        wait_for_purchase(recovery_order, product, token)
        recovered = request(8005, "/payments/transactions/" + transaction_id, token=token)
        assert recovered["status"] == "PAID", recovered
        assert request(8002, f'/products/{product["id"]}')["stock"] == 1
        print("OK: caida despues de reservar recuperada automaticamente, sin segundo descuento.")
        complete = True
    finally:
        if complete or not orders:
            cleanup(user, product, orders)
        else:
            print("Datos de prueba conservados para diagnostico:", marker)


if __name__ == "__main__":
    main()

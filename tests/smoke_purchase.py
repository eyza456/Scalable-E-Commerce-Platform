"""Prueba HTTP local con datos propios. Limpia solo los registros que crea."""
import json
import http.client
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def service_code(service, code, *args):
    return subprocess.run(
        ["docker", "compose", "exec", "-T", service, "python", "-c", code, *map(str, args)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def request(port, path, method="GET", body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        f"http://localhost:{port}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status, content = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, content = exc.code, exc.read()
    if status != expected:
        raise AssertionError(f"{method} {path}: HTTP {status}, esperado {expected}: {content!r}")
    return json.loads(content) if content else None


def wait_for_inventory(order_id):
    # Stock ya disminuye al reservar; esperar CONSUMED prueba tambien el consumidor.
    service_code("product-service", '''
import sys,time
from sqlalchemy import text
from app.database import engine
deadline=time.monotonic()+20
with engine.connect() as c:
    while True:
        count=c.execute(text("SELECT count(*) FROM inventory_reservations r JOIN processed_payment_events e ON r.transaction_id=e.transaction_id WHERE r.order_id=:id AND r.status='CONSUMED'"), {"id":int(sys.argv[1])}).scalar()
        if count == 1:
            break
        assert time.monotonic()<deadline,"El consumidor no confirmo la reserva"
        time.sleep(0.2)
''', order_id)


def main():
    marker = "stability-" + uuid.uuid4().hex
    user = product = order = payment = None
    delivered = False
    try:
        for port in range(8001, 8007):
            deadline = time.monotonic() + 30
            while True:
                try:
                    assert request(port, "/health")["status"] == "healthy"
                    break
                except (OSError, http.client.HTTPException):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.5)
        request(8002, "/products/1/stock/decrease", "PATCH", {"quantity": 1}, expected=401)
        user = request(8001, "/auth/register", "POST", {
            "name": marker, "email": marker + "@example.com", "password": "Test-Stability-2026",
        }, expected=201)
        token = request(8001, "/auth/login", "POST", {
            "email": user["email"], "password": "Test-Stability-2026",
        })["access_token"]
        assert request(8001, "/users/me", token=token)["id"] == user["id"]
        request(8001, "/users/admin-test", token=token, expected=403)
        request(8002, "/products/1/stock/decrease", "PATCH", {"quantity": 1}, token, expected=403)
        # Token administrativo efimero exclusivo para crear el producto de prueba.
        admin = service_code("payment-service", '''
import sys
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({"sub": sys.argv[1], "email": sys.argv[2], "role": "admin",
                  "exp": datetime.now(timezone.utc) + timedelta(minutes=2)},
                 settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM))
''', user["id"], user["email"])
        product = request(8002, "/products/", "POST", {
            "name": marker, "price": "12.30", "stock": 3,
        }, admin, expected=201)
        request(8003, "/cart/items", "POST", {"product_id": product["id"], "quantity": 2}, token, expected=201)
        order = request(8004, "/orders", "POST", token=token, expected=201)
        payment = request(8005, "/payments", "POST", {"order_id": order["id"], "method": "card"}, token, expected=201)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            current_order = request(8004, f'/orders/{order["id"]}', token=token)
            current_product = request(8002, f'/products/{product["id"]}')
            if current_order["status"] == "PAID" and current_product["stock"] == 1:
                delivered = True
                break
            time.sleep(0.5)
        assert delivered, "No se confirmaron pedido e inventario dentro de 35 segundos"
        wait_for_inventory(order["id"])
        request(8005, "/payments", "POST", {"order_id": order["id"], "method": "card"}, token, expected=400)
        counts = json.loads(service_code("payment-service", '''
import json,sys
from sqlalchemy import text
from app.database import engine
with engine.connect() as conn:
    rows=conn.execute(text("SELECT status FROM outbox_events WHERE aggregate_id=:id"), {"id":int(sys.argv[1])}).scalars().all()
print(json.dumps(rows))
''', order["id"]))
        assert len(counts) == 3 and set(counts) == {"PUBLISHED"}, counts
        print("OK: 6 health checks; perfil de cliente; permisos; carrito -> pedido -> pago -> stock; Outbox publicado; doble pago rechazado.")
    finally:
        # No borrar una compra con eventos pendientes: conservarla para diagnostico.
        if payment and not delivered:
            print("Compra de prueba conservada para diagnostico:", marker)
            raise RuntimeError("Compra de prueba pendiente; revisar eventos antes de limpiarla")
        if order:
            service_code("payment-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as c:
    p={"id":int(sys.argv[1])}
    c.execute(text("DELETE FROM outbox_events WHERE aggregate_id=:id"),p)
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
        if product:
            service_code("product-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as c:
    if sys.argv[2] != "None":
        c.execute(text("DELETE FROM processed_payment_events WHERE order_id=:id"), {"id":int(sys.argv[2])})
        c.execute(text("DELETE FROM inventory_reservations WHERE order_id=:id"), {"id":int(sys.argv[2])})
    c.execute(text("DELETE FROM products WHERE id=:id AND name=:name"), {"id":int(sys.argv[1]),"name":sys.argv[3]})
''', product["id"], order["id"] if order else None, marker)
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
    c.execute(text("DELETE FROM users WHERE id=:id AND email=:email"), {"id":int(sys.argv[1]),"email":sys.argv[2]})
''', user["id"], user["email"])


if __name__ == "__main__":
    main()

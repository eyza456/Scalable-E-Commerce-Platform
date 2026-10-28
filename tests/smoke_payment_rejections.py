"""Rechazos simulados por gateway: sin stock/eventos y reintento aprobado."""
import json
from pathlib import Path
import uuid

from gateway_stability import api
from smoke_purchase import service_code, wait_for_inventory
from smoke_inventory import cleanup


def main():
    marker = "rejections-" + uuid.uuid4().hex
    user = product = None
    orders = []
    complete = False
    results = {}
    try:
        user = api("/api/auth/register", "POST", {
            "name": marker, "email": marker + "@example.com", "password": "Test-Rejection-2026",
        }, expected=201)
        token = api("/api/auth/login", "POST", {
            "email": user["email"], "password": "Test-Rejection-2026",
        })["access_token"]
        admin = service_code("payment-service", '''
import sys
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({"sub":sys.argv[1],"email":sys.argv[2],"role":"admin","exp":datetime.now(timezone.utc)+timedelta(minutes=5)},settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
''', user["id"], user["email"])
        product = api("/api/products/", "POST", {"name": marker, "price": "15.00", "stock": 10}, admin, expected=201)
        api("/api/cart/items", "POST", {"product_id": product["id"], "quantity": 2}, token, expected=201)
        order = api("/api/orders", "POST", token=token, expected=201)
        orders.append(order)
        api("/api/payments", "POST", {"order_id": order["id"], "method": "card", "simulation_result": "unknown"}, token, expected=422)
        for result, code in (("insufficient_funds", "INSUFFICIENT_FUNDS"),
                             ("expired_card", "EXPIRED_CARD"), ("card_declined", "CARD_DECLINED")):
            rejection = api("/api/payments", "POST", {
                "order_id": order["id"], "method": "card", "simulation_result": result,
            }, token, expected=409)["detail"]
            assert rejection["code"] == code, rejection
            transaction = api("/api/payments/transactions/" + rejection["transaction_id"], token=token)
            assert transaction["status"] == "REJECTED" and transaction["rejection_code"] == code
            assert transaction["processed_at"] is not None
            assert api(f'/api/products/{product["id"]}')["stock"] == 10
            assert api(f'/api/orders/{order["id"]}', token=token)["status"] == "PENDING"
            results[result] = {"http_status": 409, "code": code, "processed_at": transaction["processed_at"]}
        counts = json.loads(service_code("payment-service", '''
import json,sys
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
    p={"id":int(sys.argv[1])}
    print(json.dumps({"rejected":c.execute(text("SELECT count(*) FROM payments WHERE order_id=:id AND status='REJECTED'"),p).scalar(),
                      "outbox":c.execute(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id"),p).scalar()}))
''', order["id"]))
        assert counts == {"rejected": 3, "outbox": 0}, counts
        reserved = service_code("product-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
    print(c.execute(text("SELECT count(*) FROM inventory_reservations WHERE order_id=:id"),{"id":int(sys.argv[1])}).scalar())
''', order["id"])
        assert int(reserved) == 0
        results["before_retry"] = {**counts, "reservations": 0, "stock": 10}
        payment = api("/api/payments", "POST", {"order_id": order["id"], "method": "card"}, token, expected=201)
        assert payment["status"] == "PAID" and payment["rejection_code"] is None
        wait_for_inventory(order["id"])
        assert api(f'/api/products/{product["id"]}')["stock"] == 8
        results["approved_retry"] = {"http_status": 201, "stock": 8}
        complete = True
    finally:
        if complete or not orders:
            cleanup(user, product, orders)
        else:
            print("Datos conservados para diagnostico:", marker)
    Path("docs/auditoria/rechazos-pago-resultados.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("OK: tres rechazos simulados, sin reservas/eventos, fecha y motivo persistidos; reintento aprobado con un descuento.")


if __name__ == "__main__":
    main()

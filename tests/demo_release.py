"""Demostracion reproducible del MVP por gateway, con datos propios y limpieza."""
import json
from pathlib import Path
import time
import uuid
from datetime import datetime, timezone

from gateway_stability import api, exchange
from smoke_purchase import service_code, wait_for_inventory
from smoke_inventory import cleanup


def main():
    marker = "demo-" + uuid.uuid4().hex
    user = product = category = None
    orders, steps = [], []
    complete = False

    def step(name, **result):
        steps.append({"step": name, **result})
        print(f"{len(steps):02}. OK: {name}", flush=True)

    try:
        user = api("/api/auth/register", "POST", {
            "name": marker, "email": marker + "@example.com", "password": "Demo-Test-2026",
        }, expected=201)
        token = api("/api/auth/login", "POST", {"email": user["email"], "password": "Demo-Test-2026"})["access_token"]
        profile = api("/api/users/me", "PUT", {"name": "Cliente de demostracion"}, token)
        token = profile["access_token"]
        assert api("/api/users/me", token=token)["name"] == "Cliente de demostracion"
        step("Registro, login JWT y actualizacion del perfil")
        # Fixture administrativo efimero: no cambia roles de usuarios reales.
        admin = service_code("payment-service", '''
import sys
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({'sub':sys.argv[1],'email':sys.argv[2],'role':'admin','exp':datetime.now(timezone.utc)+timedelta(minutes=5)},settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
''', user["id"], user["email"])
        category = api("/api/categories", "POST", {"name": marker}, admin, expected=201)
        product = api("/api/products/", "POST", {"name": marker, "price": "15.00", "stock": 5,
                        "category_id": category["id"]}, admin, expected=201)
        catalog = api(f'/api/products/?category_id={category["id"]}&available=true')
        assert [p["id"] for p in catalog] == [product["id"]]
        step("Categoria, producto y catalogo disponible", stock=5)
        api("/api/cart/items", "POST", {"product_id": product["id"], "quantity": 1}, token, expected=201)
        api(f'/api/cart/items/{product["id"]}', "PUT", {"quantity": 2}, token)
        assert float(api("/api/cart", token=token)["total"]) == 30
        api(f'/api/cart/items/{product["id"]}', "DELETE", token=token)
        assert api("/api/cart", token=token)["items"] == []
        api("/api/cart/items", "POST", {"product_id": product["id"], "quantity": 1}, token, expected=201)
        api("/api/cart", "DELETE", token=token)
        assert api("/api/cart", token=token)["items"] == []
        step("Carrito: agregar, modificar, eliminar articulo y vaciar")
        api("/api/cart/items", "POST", {"product_id": product["id"], "quantity": 2}, token, expected=201)
        version = api("/api/cart", token=token)["version"]
        status, order, _, _ = exchange("/api/orders", "POST", token=token, headers={"Idempotency-Key": version})
        assert status == 201 and float(order["total"]) == 30
        orders.append(order)
        status, repeated, _, _ = exchange("/api/orders", "POST", token=token, headers={"Idempotency-Key": version})
        assert status == 200 and repeated["id"] == order["id"]
        step("Pedido desde carrito y repeticion idempotente", total=30, orders_created=1)
        rejected = api("/api/payments", "POST", {"order_id": order["id"], "method": "card",
                        "simulation_result": "card_declined"}, token, expected=409)["detail"]
        assert rejected["code"] == "CARD_DECLINED"
        transaction = api("/api/payments/transactions/" + rejected["transaction_id"], token=token)
        assert transaction["processed_at"] and transaction["rejection_code"] == "CARD_DECLINED"
        assert api(f'/api/orders/{order["id"]}', token=token)["status"] == "PENDING"
        assert api(f'/api/products/{product["id"]}')["stock"] == 5
        step("Pago rechazado, motivo y fecha; pedido pendiente sin descontar stock")
        payment = api("/api/payments", "POST", {"order_id": order["id"], "method": "card"}, token, expected=201)
        assert payment["status"] == "PAID" and payment["processed_at"]
        wait_for_inventory(order["id"])
        deadline = time.monotonic() + 30
        while api(f'/api/orders/{order["id"]}', token=token)["status"] != "PAID":
            assert time.monotonic() < deadline
            time.sleep(0.5)
        assert api(f'/api/products/{product["id"]}')["stock"] == 3
        step("Pago aprobado, pedido PAID y reserva consumida una vez", stock=3)
        api(f'/api/orders/{order["id"]}/status', "PATCH", {"status": "PROCESSING"}, token, expected=403)
        for state in ("PROCESSING", "SHIPPED", "DELIVERED"):
            updated = api(f'/api/orders/{order["id"]}/status', "PATCH", {"status": state}, admin)
            assert updated["status"] == state
        step("Administracion autorizada: PROCESSING, SHIPPED y DELIVERED")
        api("/api/cart/items", "POST", {"product_id": product["id"], "quantity": 1}, token, expected=201)
        pending = api("/api/orders", "POST", token=token, expected=201)
        orders.append(pending)
        cancelled = api(f'/api/orders/{pending["id"]}/cancel', "POST", token=token)
        assert cancelled["status"] == "CANCELLED"
        assert api(f'/api/orders/{pending["id"]}/cancel', "POST", token=token)["status"] == "CANCELLED"
        assert api(f'/api/products/{product["id"]}')["stock"] == 3
        step("Cancelacion idempotente de pedido pendiente", stock=3)
        history = api("/api/orders", token=token)
        assert {p["id"]: p["status"] for p in history} == {order["id"]: "DELIVERED", pending["id"]: "CANCELLED"}
        step("Historial y detalle privados", statuses=["DELIVERED", "CANCELLED"])
        complete = True
    finally:
        if complete or not orders:
            cleanup(user, product, orders)
            if category is not None:
                api(f'/api/categories/{category["id"]}', "DELETE", token=admin, expected=204)
        else:
            print("Datos conservados para diagnostico:", marker)
    output = Path(__file__).resolve().parents[1] / "docs/entrega/demo-resultados.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"executed_at": datetime.now(timezone.utc).isoformat(), "status": "passed",
                                 "steps": steps, "fixtures_cleaned": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK: demostracion completa; datos propios eliminados.")


if __name__ == "__main__":
    main()

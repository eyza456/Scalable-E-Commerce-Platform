"""Pruebas HTTP del gateway real. Requiere Docker Compose activo."""
import json
import os
import re
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid

from smoke_purchase import service_code, wait_for_inventory
from smoke_inventory import cleanup

BASE = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def exchange(path, method="GET", body=None, token=None, headers=None, follow=True):
    outgoing = {"Content-Type": "application/json", **(headers or {})}
    if token:
        outgoing["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, method=method, headers=outgoing,
        data=json.dumps(body).encode("utf-8") if body is not None else None)
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(req, timeout=35)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        data = response.read()
        return response.code, json.loads(data) if data else None, response.headers, response.url


def api(path, method="GET", body=None, token=None, expected=200):
    status, data, _, _ = exchange(path, method, body, token)
    if status != expected:
        raise AssertionError(f"{method} {path}: HTTP {status}, esperado {expected}: {data}")
    return data


class GatewayRoutes(unittest.TestCase):
    def test_gateway_health_and_request_id(self):
        status, data, headers, _ = exchange("/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["service"], "API Gateway")
        self.assertRegex(headers["X-Request-ID"], r"^[0-9a-f]{32}$")

    def test_root_lists_public_routes(self):
        data = api("/")
        self.assertEqual(len(data["routes"]), 7)
        self.assertIn("/api/categories", data["routes"])

    def test_public_catalog_and_query_validation(self):
        self.assertIsInstance(api("/api/products/?limit=1"), list)
        self.assertIsInstance(api("/api/categories?limit=1"), list)
        for path in ("/api/products/?limit=101", "/api/categories?skip=-1"):
            with self.subTest(path=path):
                api(path, expected=422)

    def test_protected_routes_keep_backend_authentication(self):
        for path in ("/api/users/me", "/api/cart", "/api/orders", "/api/payments/transactions/TX-MISSING"):
            with self.subTest(path=path):
                api(path, expected=401)

    def test_json_body_reaches_auth_service(self):
        api("/api/auth/login", "POST", {"email": "invalid"}, expected=422)

    def test_internal_paths_are_not_public_even_with_key_header(self):
        for method, path in (
            ("GET", "/api/orders/internal/1"),
            ("GET", "/api/payments/internal/transactions/TX-MISSING"),
            ("POST", "/api/payments/internal/orders/1/cancel"),
            ("POST", "/api/inventory/internal/reservations/TX-MISSING"),
            ("POST", "/api/inventory/internal/orders/1/release"),
        ):
            with self.subTest(path=path):
                status, _, _, _ = exchange(path, method, headers={"X-Internal-Service-Key": "untrusted"})
                self.assertEqual(status, 404)

    def test_normalized_internal_paths_remain_blocked(self):
        for path in ("/api/orders/%69nternal/1", "/api//orders/internal/1",
                     "/api/products/../orders/internal/1", "/api/payments/%69nternal/transactions/TX"):
            with self.subTest(path=path):
                api(path, expected=404)

    def test_unknown_routes_do_not_reach_arbitrary_backends(self):
        for path in ("/docs", "/api/docs", "/api/productsx", "/api/notifications", "/unknown"):
            with self.subTest(path=path):
                api(path, expected=404)

    def test_redirects_keep_api_prefix_query_and_external_port(self):
        for path, expected_path in (("/api/products?limit=1", "/api/products/"),
                                    ("/api/categories/", "/api/categories")):
            with self.subTest(path=path):
                status, _, headers, _ = exchange(path, follow=False)
                self.assertEqual(status, 307)
                target = urllib.parse.urljoin(BASE + path, headers["Location"])
                self.assertEqual(urllib.parse.urlsplit(target).netloc, urllib.parse.urlsplit(BASE).netloc)
                self.assertEqual(urllib.parse.urlsplit(target).path, expected_path)
                if "?" in path:
                    self.assertEqual(urllib.parse.urlsplit(target).query, "limit=1")
                self.assertEqual(exchange(path)[0], 200)


class GatewayPurchase(unittest.TestCase):
    def test_profile_catalog_cart_purchase_history_and_cancel_through_gateway(self):
        marker = "gateway-test-" + uuid.uuid4().hex
        user = product = category = None
        orders = []
        complete = False
        admin = None
        try:
            user = api("/api/auth/register", "POST", {
                "name": marker, "email": marker + "@example.com", "password": "Gateway-Test-2026",
            }, expected=201)
            token = api("/api/auth/login", "POST", {
                "email": user["email"], "password": "Gateway-Test-2026",
            })["access_token"]
            profile = api("/api/users/me", "PUT", {"name": "Gateway updated user"}, token)
            self.assertEqual(profile["name"], "Gateway updated user")
            token = profile["access_token"]
            api("/api/users/me", "PUT", {"role": "admin"}, token, expected=422)
            api("/api/categories", "POST", {"name": marker}, token, expected=403)
            admin = service_code("payment-service", '''
import sys
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({"sub":sys.argv[1],"email":sys.argv[2],"role":"admin",
                  "exp":datetime.now(timezone.utc)+timedelta(minutes=5)},
                 settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
''', user["id"], user["email"])
            category = api("/api/categories", "POST", {"name": marker}, admin, expected=201)
            product = api("/api/products/", "POST", {
                "name": marker + " Laptop 100%_é", "price": "12.30", "stock": 3, "category_id": category["id"],
            }, admin, expected=201)
            query = urllib.parse.urlencode({"name": "100%_é", "category_id": category["id"], "available": "true", "limit": 1})
            self.assertEqual([p["id"] for p in api("/api/products/?" + query)], [product["id"]])
            api("/api/cart/items", "POST", {"product_id": product["id"], "quantity": 1}, token, expected=201)
            api("/api/cart/items/" + str(product["id"]), "PUT", {"quantity": 2}, token)
            self.assertEqual(len(api("/api/cart", token=token)["items"]), 1)
            paid = api("/api/orders", "POST", token=token, expected=201)
            orders.append(paid)
            payment = api("/api/payments", "POST", {"order_id": paid["id"], "method": "card"}, token, expected=201)
            self.assertEqual(payment["status"], "PAID")
            wait_for_inventory(paid["id"])
            deadline = time.monotonic() + 25
            while api(f'/api/orders/{paid["id"]}', token=token)["status"] != "PAID":
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.2)
            self.assertEqual(api(f'/api/products/{product["id"]}')["stock"], 1)
            api(f'/api/orders/{paid["id"]}/cancel', "POST", token=token, expected=409)
            api("/api/payments", "POST", {"order_id": paid["id"], "method": "card"}, token, expected=400)
            api("/api/cart/items", "POST", {"product_id": product["id"], "quantity": 1}, token, expected=201)
            pending = api("/api/orders", "POST", token=token, expected=201)
            orders.append(pending)
            cancelled = api(f'/api/orders/{pending["id"]}/cancel', "POST", token=token)
            self.assertEqual(cancelled["status"], "CANCELLED")
            history = api("/api/orders?status=CANCELLED&limit=1", token=token)
            self.assertEqual([o["id"] for o in history], [pending["id"]])
            self.assertEqual(api(f'/api/products/{product["id"]}')["stock"], 1)
            api(f'/api/categories/{category["id"]}', "DELETE", token=admin, expected=409)
            api(f'/api/products/{product["id"]}', "PUT", {"category_id": None}, admin)
            api(f'/api/categories/{category["id"]}', "DELETE", token=admin, expected=204)
            category = None
            complete = True
        finally:
            if complete or not orders:
                cleanup(user, product, orders)
                if category is not None:
                    api(f'/api/categories/{category["id"]}', "DELETE", token=admin, expected=204)
            else:
                print("Compra de prueba conservada para diagnostico:", marker)


if __name__ == "__main__":
    unittest.main(verbosity=2)

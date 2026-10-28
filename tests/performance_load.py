"""Carga cerrada por gateway sobre proyecto Compose independiente, sin librerias host."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import platform
import subprocess
import threading
import time
from urllib.parse import urlsplit

from fresh_install import Installation, ROOT
from performance_metrics import summarize, evaluate

OUT = ROOT / "docs/rendimiento"


class RequestFailed(Exception):
    pass


class Client:
    def __init__(self, base, user, phase, goals, sink):
        address = urlsplit(base)
        self.connection = http.client.HTTPConnection(address.hostname, address.port, timeout=goals["request_timeout_seconds"])
        self.user, self.phase, self.goals, self.sink = user, phase, goals, sink

    def call(self, operation, method, path, body=None, expected=(200,), headers=None):
        outgoing = {"Content-Type": "application/json", "Authorization": "Bearer " + self.user["token"], **(headers or {})}
        start = time.perf_counter()
        status, data, ok = 0, None, False
        try:
            self.connection.request(method, path, json.dumps(body) if body is not None else None, outgoing)
            response = self.connection.getresponse()
            status = response.status
            data = json.loads(response.read())
            ok = status in expected
        except (OSError, http.client.HTTPException, ValueError):
            self.connection.close()
        self.sink.append({"phase": self.phase, "vu": self.user["index"], "operation": operation,
                          "ms": (time.perf_counter() - start) * 1000, "status": status, "ok": ok})
        if not ok:
            raise RequestFailed(f"{operation}: HTTP {status}")
        return data

    def cycle(self, product_id, deadline, flows):
        # 12 consultas de navegacion por compra; sondeos se contabilizan aparte.
        for _ in range(3):
            catalog = self.call("catalog", "GET", "/api/products/?available=true&limit=20")
            if not catalog:
                raise RequestFailed("Catalogo vacio")
            product = self.call("product", "GET", f"/api/products/{product_id}")
            profile = self.call("profile", "GET", "/api/users/me")
            history = self.call("history", "GET", "/api/orders?limit=20")
            if product["stock"] <= 0 or profile["id"] != self.user["id"] or any(p["user_id"] != self.user["id"] for p in history):
                raise RequestFailed("Invariante de lectura no satisfecha")
        if time.monotonic() >= deadline:
            return
        start = time.perf_counter()
        flow_ok = False
        try:
            self.call("cart_add", "POST", "/api/cart/items", {"product_id": product_id, "quantity": 1}, expected=(201,))
            cart = self.call("cart_read", "GET", "/api/cart")
            order = self.call("checkout", "POST", "/api/orders", expected=(200, 201, 202),
                              headers={"Idempotency-Key": cart["version"]})
            expiry = time.monotonic() + self.goals["flow_timeout_seconds"]
            while "id" not in order:
                if time.monotonic() > expiry:
                    raise RequestFailed("Checkout no resuelto a tiempo")
                time.sleep(0.25)
                order = self.call("checkout_poll", "GET", "/api/orders/checkouts/" + order["checkout_id"], expected=(200, 202))
            if float(order["total"]) != 10 or order["user_id"] != self.user["id"]:
                raise RequestFailed("Total/propietario de pedido incorrecto")
            payment = self.call("payment", "POST", "/api/payments", {"order_id": order["id"], "method": "card"}, expected=(201, 202))
            if payment["status"] not in ("PAID", "PENDING"):
                raise RequestFailed("Resultado de pago inesperado")
            while True:
                state = self.call("order_poll", "GET", f'/api/orders/{order["id"]}')
                if state["status"] == "PAID":
                    break
                if time.monotonic() > expiry:
                    raise RequestFailed("Pago no reflejado en pedido a tiempo")
                time.sleep(0.5)
            flows.append({"order_id": order["id"], "user_id": self.user["id"], "product_id": product_id})
            flow_ok = True
        finally:
            self.sink.append({"phase": self.phase, "vu": self.user["index"], "operation": "purchase_flow",
                              "ms": (time.perf_counter() - start) * 1000, "status": 200 if flow_ok else 0, "ok": flow_ok})


class Performance(Installation):
    def __init__(self, goals, quick=False):
        super().__init__()
        self.goals, self.quick = goals, quick
        self.samples, self.flows, self.failures, self.resources = [], [], [], []
        self.stop_resources = threading.Event()
        self.resource_thread = None
        self.active_phase = "setup"
        self.result["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        self.result["goals"] = goals
        self.result["mode"] = "smoke-not-acceptance" if quick else "acceptance-local"
        self.result["host"] = {"platform": platform.platform(), "python": platform.python_version()}

    def note(self, message):
        for value in self.hidden:
            message = message.replace(value, "<redacted>")
        with (OUT / "ejecucion.log").open("a", encoding="utf-8") as log:
            log.write(message + "\n")

    def monitor(self, ids):
        while not self.stop_resources.is_set():
            try:
                lines = self.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids], log=False, timeout=30)
                self.resources.append({"at": datetime.now(timezone.utc).isoformat(), "phase": self.active_phase,
                                       "containers": [json.loads(line) for line in lines.splitlines()]})
            except Exception as exc:
                self.resources.append({"phase": self.active_phase, "error": type(exc).__name__})
            self.stop_resources.wait(5)

    def worker(self, user, phase, deadline, record=True):
        client = Client(self.base, user, phase, self.goals, self.samples if record else [])
        try:
            while time.monotonic() < deadline:
                client.cycle(self.product_id, deadline, self.flows)
        except Exception as exc:
            self.failures.append({"phase": phase, "vu": user["index"], "error": str(exc)})
        finally:
            client.connection.close()

    def drain(self):
        return json.loads(self.py("payment-service", '''
import json
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
    print(json.dumps({'pending_payments':c.execute(text("SELECT count(*) FROM payments WHERE status='PENDING'")).scalar(),
                      'pending_events':c.execute(text("SELECT count(*) FROM outbox_events WHERE status!='PUBLISHED'")).scalar()}))
''', log=False))

    def stage(self, concurrency, seconds, record=True):
        phase = f"vu-{concurrency}" if record else "warmup"
        self.active_phase = phase
        self.phase(f"Carga {phase}: {concurrency} usuarios, {seconds}s...")
        start = time.perf_counter()
        deadline = time.monotonic() + seconds
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(lambda user: self.worker(user, phase, deadline, record), self.users[:concurrency]))
        elapsed = time.perf_counter() - start
        summary = summarize([s for s in self.samples if s["phase"] == phase], elapsed)
        summary.update({"concurrency": concurrency, "scheduled_seconds": seconds,
                        "worker_failures": [f for f in self.failures if f["phase"] == phase]})
        if record:
            self.phase(f"Fin {phase}: {summary['requests']} solicitudes, {summary['error_percent']:.2f}% errores, {summary['useful_requests_per_second']:.1f} req/s utiles")
        else:
            self.phase("Fin calentamiento; muestras excluidas de los percentiles")
        return summary

    def exercise(self):
        info = json.loads(self.run(["docker", "info", "--format", "{{json .}}"], log=False))
        self.result["host"].update({"docker_cpus": info["NCPU"], "docker_memory_bytes": info["MemTotal"],
                                    "docker_os": info["OperatingSystem"], "docker_server": info["ServerVersion"]})
        self.result["dependency_versions"] = json.loads(self.py("payment-service", '''
import json,sys,importlib.metadata as m
print(json.dumps({'python':sys.version.split()[0],**{name:m.version(name) for name in ['fastapi','sqlalchemy','uvicorn','httpx','pika','psycopg2-binary']}}))
''', log=False))
        self.product_id = int(self.py("product-service", '''
from decimal import Decimal
from sqlalchemy.orm import Session
from app.database import engine
from app.models import Product,Category
with Session(engine) as db:
    category=Category(name='Performance');db.add(category);db.flush()
    items=[Product(name=f'Perf product {i:03}',price=Decimal('10.00'),stock=1000000,is_active=True,category_id=category.id) for i in range(100)]
    db.add_all(items);db.commit();print(items[0].id)
''', log=False))
        self.users = []
        self.phase(f"Preparando {max(self.goals['concurrency'])} usuarios y 100 productos; registro/login fuera de la medicion...")
        for index in range(max(self.goals["concurrency"])):
            email = f"perf-{index}@example.com"
            user = self.api("/api/auth/register", "POST", {"name": f"Perf user {index}", "email": email, "password": "Performance-Test-2026"}, expected=201)
            token = self.api("/api/auth/login", "POST", {"email": email, "password": "Performance-Test-2026"})["access_token"]
            self.users.append({"index": index, "id": user["id"], "token": token})
        self.result["dataset"] = {"products": 100, "users": len(self.users), "stock_per_product": 1000000,
                                  "catalog_page_size": 20, "history_page_size": 20, "shared_purchase_product": True}
        ids = self.dc("ps", "-q", log=False).splitlines()
        self.resource_thread = threading.Thread(target=self.monitor, args=(ids,), daemon=True)
        self.resource_thread.start()
        self.stage(min(5, len(self.users)), self.goals["warmup_seconds"], record=False)
        self.wait(lambda: not any(self.drain().values()), timeout=60)
        self.result["stages"] = [self.stage(n, self.goals["stage_seconds"]) for n in self.goals["concurrency"]]
        self.active_phase = "drain"
        self.phase("Verificando pedidos, pagos, descuentos y eventos despues de la carga...")
        self.wait(lambda: not any(self.drain().values()), timeout=90)
        invariants = {}
        invariants["payments"] = json.loads(self.py("payment-service", '''
import json
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
    print(json.dumps({'paid':c.execute(text("SELECT count(*) FROM payments WHERE status='PAID'")).scalar(),
       'other':c.execute(text("SELECT count(*) FROM payments WHERE status!='PAID'")).scalar(),
       'duplicate_orders':c.execute(text("SELECT count(*) FROM (SELECT order_id FROM payments WHERE status='PAID' GROUP BY order_id HAVING count(*)>1) s")).scalar(),
       'published':c.execute(text("SELECT count(*) FROM outbox_events WHERE status='PUBLISHED'")).scalar()}))
''', log=False))
        invariants["orders"] = json.loads(self.py("order-service", '''
import json
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
    print(json.dumps({'paid':c.execute(text("SELECT count(*) FROM orders WHERE status='PAID'")).scalar(),
       'other':c.execute(text("SELECT count(*) FROM orders WHERE status!='PAID'")).scalar(),
       'unfinished_checkouts':c.execute(text("SELECT count(*) FROM checkouts WHERE state!='COMPLETE'")).scalar()}))
''', log=False))
        invariants["inventory"] = json.loads(self.py("product-service", '''
import json,sys
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
    print(json.dumps({'stock':c.execute(text("SELECT stock FROM products WHERE id=:id"),{'id':int(sys.argv[1])}).scalar(),
      'consumed':c.execute(text("SELECT count(*) FROM inventory_reservations WHERE status='CONSUMED'")).scalar(),
      'other':c.execute(text("SELECT count(*) FROM inventory_reservations WHERE status!='CONSUMED'")).scalar(),
      'processed_events':c.execute(text("SELECT count(*) FROM processed_payment_events")).scalar()}))
''', self.product_id, log=False))
        count = len(self.flows)
        correct = (not self.failures and len({f["order_id"] for f in self.flows}) == count
                   and invariants["payments"] == {"paid": count, "other": 0, "duplicate_orders": 0, "published": count * 3}
                   and invariants["orders"] == {"paid": count, "other": 0, "unfinished_checkouts": 0}
                   and invariants["inventory"] == {"stock": 1000000 - count, "consumed": count, "other": 0, "processed_events": count})
        self.result["invariants"] = {"passed": correct, "completed_flows_including_warmup": count, **invariants}
        target = next(stage for stage in self.result["stages"] if stage["concurrency"] == self.goals["target_concurrency"])
        self.result["evaluation"] = evaluate(target, self.goals, correct)
        self.result["status"] = ("smoke-completed" if self.quick and correct else "passed" if not self.quick and self.result["evaluation"]["passed"] else "targets-not-met")

    def cleanup(self):
        self.stop_resources.set()
        if self.resource_thread:
            self.resource_thread.join(timeout=35)
        super().cleanup()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Solo valida el instrumento; no acepta objetivos")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ejecucion.log").write_text("", encoding="utf-8")
    goal_path = Path(__file__).with_name("performance_goals.json")
    goals = json.loads(goal_path.read_text(encoding="utf-8"))
    if args.smoke:
        goals.update({"concurrency": [1, 2], "target_concurrency": 2, "stage_seconds": 5, "warmup_seconds": 2})
    test = Performance(goals, args.smoke)
    test.result["goals_file_sha256"] = hashlib.sha256(goal_path.read_bytes()).hexdigest()
    existing = test.run(["docker", "ps", "-q"], log=False).splitlines()
    test.result["host"]["other_running_containers"] = len(existing)
    name = "smoke" if args.smoke else "resultado"
    try:
        test.verify()
    except Exception as exc:
        test.result["status"] = "execution-failed"
        test.result["error"] = str(exc)
        if test.compose:
            try:
                test.dc("logs", "--no-color", "--tail", "50", timeout=60)
            except Exception:
                pass
        raise
    finally:
        try:
            test.cleanup()
        except Exception as exc:
            test.result["status"] = "cleanup-failed"
            test.result["cleanup_error"] = str(exc)
            raise
        finally:
            (OUT / f"{name}.json").write_text(json.dumps(test.result, ensure_ascii=False, indent=2), encoding="utf-8")
            (OUT / f"{name}-muestras.jsonl").write_text("\n".join(json.dumps(s) for s in test.samples) + "\n", encoding="utf-8")
            (OUT / f"{name}-recursos.json").write_text(json.dumps(test.resources, indent=2), encoding="utf-8")
    print("Resultado:", test.result["status"], flush=True)
    if (args.smoke and not test.result["invariants"]["passed"]) or (not args.smoke and not test.result["evaluation"]["passed"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()

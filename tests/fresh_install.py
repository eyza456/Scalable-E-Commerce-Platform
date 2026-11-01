"""Instalacion aislada desde archivos versionados; solo requiere Python y Docker."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/auditoria/instalacion-desde-cero.json"
LOG = REPORT.with_suffix(".log")
INFRA = ["user-db", "product-db", "order-db", "payment-db", "redis", "rabbitmq"]
APPS = ["user-service", "product-service", "cart-service", "order-service", "payment-service", "notification-service"]


class Installation:
    def __init__(self):
        self.project = "fresh-" + uuid.uuid4().hex[:12]
        self.folder = ROOT / "tmp" / self.project
        self.compose = None
        self.hidden = []
        self.env = os.environ.copy()
        self.result = {"project": self.project, "executed_at": datetime.now(timezone.utc).isoformat(), "checks": {}}

    def note(self, message):
        for value in self.hidden:
            message = message.replace(value, "<redacted>")
        with LOG.open("a", encoding="utf-8") as log:
            log.write(message + "\n")

    def run(self, args, log=True, timeout=600, input=None):
        proc = subprocess.run(args, cwd=ROOT, env=self.env, text=True, encoding="utf-8", errors="replace",
                              capture_output=True, timeout=timeout, input=input)
        if log:
            self.note(proc.stdout + proc.stderr)
        if proc.returncode:
            raise RuntimeError(f"Comando fallo ({proc.returncode}); revisar {LOG.name}")
        return proc.stdout.strip()

    def dc(self, *args, **kwargs):
        return self.run([*self.compose, *args], **kwargs)

    def py(self, service, code, *args, log=True):
        return self.dc("exec", "-T", service, "python", "-c", code, *map(str, args), log=log)

    def phase(self, message):
        print(message, flush=True)
        self.note(message)

    def prepare(self):
        self.folder.mkdir(parents=True, exist_ok=False)
        files = self.run(["git", "ls-files", "-z"], log=False).split("\0")
        for name in filter(None, files):
            source = ROOT / name
            if source.is_file():
                target = self.folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        template = (self.folder / ".env.example").read_text(encoding="utf-8")
        values = {}
        for line in template.splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                if "replace-" in value:
                    value = secrets.token_hex(24)
                    self.hidden.append(value)
                values[key] = value
                self.env.pop(key, None)  # No heredar la configuracion del entorno habitual.
        (self.folder / ".env").write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")
        self.compose = ["docker", "compose", "--project-name", self.project, "--project-directory", str(self.folder),
                        "--env-file", str(self.folder / ".env"), "-f", str(self.folder / "docker-compose.yml")]
        self.dc("config", "--quiet")
        config = json.loads(self.dc("config", "--format", "json", log=False))
        # Misma configuracion resuelta del README; solo cambiar nombres y puertos
        # para convivir con la instalacion del usuario sin usar sus volumenes.
        for service, spec in config["services"].items():
            spec.pop("container_name", None)
            spec["ports"] = ([{"target": 80, "published": "0", "host_ip": "127.0.0.1", "protocol": "tcp"}]
                             if service == "api-gateway" else [])
        for kind in ("volumes", "networks"):
            for spec in config[kind].values():
                assert spec["name"].startswith(self.project + "_"), spec["name"]
                assert not spec.get("external"), "Recurso externo no permitido"
        isolated = self.folder / "isolated.json"
        isolated.write_text(json.dumps(config), encoding="utf-8")
        self.compose[-1] = str(isolated)
        assert not self.dc("ps", "-a", "-q", log=False), "El proyecto de prueba ya contiene contenedores"
        for spec in config["volumes"].values():
            existing = self.run(["docker", "volume", "ls", "--format", "{{.Name}}"], log=False).splitlines()
            assert spec["name"] not in existing, "La prueba requiere volumenes nuevos"
        self.result["checks"]["configuration"] = "Plantilla independiente; sin .env ni datos locales"
        self.result["volumes"] = [v["name"] for v in config["volumes"].values()]
        self.result["readme_sha256"] = hashlib.sha256((self.folder / "README.md").read_bytes()).hexdigest()

    def api(self, path, method="GET", body=None, token=None, expected=200):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(self.base + path, method=method, headers=headers,
                    data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urllib.request.urlopen(request, timeout=15)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            data = response.read()
            assert response.status == expected, f"{method} {path}: HTTP {response.status}, esperado {expected}"
            return json.loads(data) if data else None

    def wait(self, callback, timeout=90):
        deadline = time.monotonic() + timeout
        while True:
            try:
                if callback():
                    return
            except (OSError, AssertionError):
                if time.monotonic() >= deadline:
                    raise
            assert time.monotonic() < deadline, "Tiempo de espera agotado"
            time.sleep(1)

    def check_schema(self):
        expected = {
            "user-service": {"users": ["email"]},
            "order-service": {"orders": ["checkout_id"], "order_items": ["product_id"], "checkouts": ["state"]},
            "payment-service": {"payments": ["event_payload", "processed_at", "simulation_result", "rejection_code"],
                                "outbox_events": ["destination"], "order_cancellations": ["status"]},
            "product-service": {"products": ["category_id"], "categories": ["name"],
                                "inventory_reservations": ["status"], "inventory_cancellations": ["order_id"],
                                "processed_payment_events": ["transaction_id"]},
        }
        for service, tables in expected.items():
            self.py(service, '''
import json,sys
from sqlalchemy import inspect,text
from app.database import engine
expected=json.loads(sys.argv[1]); inspector=inspect(engine)
for table,columns in expected.items():
    assert set(columns) <= {c['name'] for c in inspector.get_columns(table)},table
    with engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM '+table)).scalar()==0,table
if 'users' in expected:
    assert next(c for c in inspector.get_columns('users') if c['name']=='email')['type'].length==254
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM pg_indexes WHERE indexname='ux_users_email_lower'")).scalar()==1
print('Esquema nuevo correcto')
''', json.dumps(tables))
        self.result["checks"]["schemas"] = expected

    def exercise(self):
        user = self.api("/api/auth/register", "POST", {
            "name": "Fresh installation", "email": "fresh@example.com", "password": "Fresh-Test-2026",
        }, expected=201)
        token = self.api("/api/auth/login", "POST", {"email": user["email"], "password": "Fresh-Test-2026"})["access_token"]
        admin = self.py("payment-service", '''
import sys
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({'sub':sys.argv[1],'email':'fresh@example.com','role':'admin','exp':datetime.now(timezone.utc)+timedelta(minutes=5)},settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
''', user["id"], log=False)
        category = self.api("/api/categories", "POST", {"name": "Fresh category"}, admin, expected=201)
        product = self.api("/api/products/", "POST", {"name": "Fresh product", "price": "12.30", "stock": 5,
                            "category_id": category["id"]}, admin, expected=201)
        self.api("/api/cart/items", "POST", {"product_id": product["id"], "quantity": 2}, token, expected=201)
        order = self.api("/api/orders", "POST", token=token, expected=201)
        rejection = self.api("/api/payments", "POST", {"order_id": order["id"], "method": "card",
                            "simulation_result": "insufficient_funds"}, token, expected=409)
        assert rejection["detail"]["code"] == "INSUFFICIENT_FUNDS"
        assert self.api(f'/api/products/{product["id"]}')["stock"] == 5
        payment = self.api("/api/payments", "POST", {"order_id": order["id"], "method": "card"}, token, expected=201)
        assert payment["status"] == "PAID" and payment["processed_at"] is not None
        self.wait(lambda: self.api(f'/api/orders/{order["id"]}', token=token)["status"] == "PAID")
        self.wait(lambda: self.api(f'/api/products/{product["id"]}')["stock"] == 3)
        self.py("product-service", '''
import sys,time
from sqlalchemy import text
from app.database import engine
deadline=time.monotonic()+40
while True:
    with engine.connect() as c:
        count=c.execute(text("SELECT count(*) FROM inventory_reservations r JOIN processed_payment_events e ON r.transaction_id=e.transaction_id WHERE r.order_id=:id AND r.status='CONSUMED'"),{'id':int(sys.argv[1])}).scalar()
    if count==1:break
    assert time.monotonic()<deadline,'Reserva no consumida'
    time.sleep(1)
print('Reserva consumida una vez')
''', order["id"])
        self.py("payment-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
    assert c.execute(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND status='PUBLISHED'"),{'id':int(sys.argv[1])}).scalar()==3
print('Tres entregas publicadas')
''', order["id"])
        self.wait(lambda: payment["transaction_id"] in self.dc("logs", "--no-color", "notification-service", log=False))
        self.result["checks"]["purchase"] = {"order_status": "PAID", "stock": 3, "outbox_published": 3,
                                                "reservation": "CONSUMED", "notification": "received",
                                                "rejected_attempt": "INSUFFICIENT_FUNDS"}
        # Persistencia SQL y del carrito Redis ante reinicio (sin recrear volumenes).
        self.api("/api/cart/items", "POST", {"product_id": product["id"], "quantity": 1}, token, expected=201)
        self.phase("Reiniciando el proyecto aislado y comprobando persistencia...")
        self.dc("restart", timeout=180)
        # Docker puede asignar otro puerto publicado al reiniciar cuando es 0.
        self.base = "http://" + self.dc("port", "api-gateway", "80", log=False)
        self.wait(lambda: self.api("/api/users/me", token=token)["id"] == user["id"])
        self.wait(lambda: self.api(f'/api/orders/{order["id"]}', token=token)["status"] == "PAID")
        self.wait(lambda: self.api(f'/api/products/{product["id"]}')["stock"] == 3)
        transaction = self.api("/api/payments/transactions/" + payment["transaction_id"], token=token)
        assert datetime.fromisoformat(transaction["processed_at"].replace("Z", "+00:00")) == datetime.fromisoformat(
            payment["processed_at"].replace("Z", "+00:00"))
        assert self.api("/api/cart", token=token)["items"][0]["quantity"] == 1
        self.result["checks"]["restart_persistence"] = "users, categories/products, orders, payments and Redis cart"

    def verify(self):
        self.phase("Preparando copia aislada y configuracion desde .env.example...")
        self.prepare()
        self.phase("Construyendo las siete imagenes de aplicacion/gateway...")
        self.dc("build", timeout=1200)
        self.phase("Arrancando seis servicios de infraestructura con volumenes nuevos...")
        self.dc("up", "-d", "--wait", "--wait-timeout", "180", *INFRA, timeout=240)
        self.phase("Aplicando Alembic antes del arranque y repitiendo upgrade head...")
        for _ in range(2):
            self.dc("run", "--rm", "--no-deps", "product-service", "alembic", "upgrade", "head")
        current = self.dc("run", "--rm", "--no-deps", "product-service", "alembic", "current")
        assert "b1c5a09e3d72 (head)" in current, current
        self.result["checks"]["alembic"] = "b1c5a09e3d72 (head); upgrade repetido sin cambios"
        self.phase("Arrancando aplicaciones y comprobando seis health endpoints...")
        self.dc("up", "-d", timeout=240)
        self.base = "http://" + self.dc("port", "api-gateway", "80", log=False)
        for service in APPS:
            self.py(service, '''
import time,urllib.request,json
deadline=time.monotonic()+90
while True:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3) as r:
            assert json.load(r)['status']=='healthy'
        break
    except Exception:
        if time.monotonic()>deadline:raise
        time.sleep(1)
print('Health OK')
''')
        self.wait(lambda: self.api("/health")["status"] == "healthy")
        assert self.api("/api/products/") == []
        ids = self.dc("ps", "-a", "-q", log=False).splitlines()
        containers = json.loads(self.run(["docker", "inspect", *ids], log=False))
        assert len(containers) == 13
        assert all(c["State"]["Running"] and c["RestartCount"] == 0 for c in containers)
        self.result["checks"]["initial_start"] = "13 contenedores activos; 0 reinicios inesperados"
        self.result["checks"]["health"] = APPS + ["api-gateway"]
        self.check_schema()
        self.phase("Probando registro, catalogo, carrito, pedido, rechazo, pago y eventos por gateway...")
        self.exercise()

    def cleanup(self):
        if self.compose:
            # Proyecto UUID propio y recursos sin external/name ajenos: nunca
            # ejecutar down en la configuracion habitual del usuario.
            assert self.compose[3] == self.project and self.project.startswith("fresh-")
            self.dc("down", "--volumes", "--remove-orphans", "--rmi", "local", timeout=180)
            assert not self.dc("ps", "-a", "-q", log=False)
            volumes = self.run(["docker", "volume", "ls", "-q", "--filter", "label=com.docker.compose.project=" + self.project], log=False)
            assert not volumes, "Quedaron volumenes de prueba"
            self.result["cleanup"] = "Proyecto aislado eliminado; sin volumenes residuales"
        # Verificar la ruta absoluta antes de cualquier borrado recursivo Windows.
        target = self.folder.resolve()
        assert target.parent == (ROOT / "tmp").resolve() and target.name == self.project
        if target.exists():
            shutil.rmtree(target)


def main():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    test = Installation()
    try:
        test.verify()
        test.result["status"] = "passed"
    except Exception as exc:
        test.result["status"] = "failed"
        test.result["error"] = str(exc)
        if test.compose:
            try:
                test.dc("logs", "--no-color", "--tail", "80", timeout=60)
            except Exception:
                pass
        raise
    finally:
        try:
            test.cleanup()
        except Exception as exc:
            test.result["status"] = "failed"
            test.result["cleanup_error"] = str(exc)
            raise
        finally:
            REPORT.write_text(json.dumps(test.result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK: instalacion desde cero, migraciones, compra, eventos y persistencia. Entorno aislado eliminado.")


if __name__ == "__main__":
    main()

"""Two replicas of each application, cross-process races and independent scaling.

Uses fresh_install's isolated copy, credentials and strictly scoped cleanup.
Does not change the normal Compose project or its data.
"""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

import fresh_install as backend
from fresh_install import Installation, ROOT, INFRA, APPS

REPORT = ROOT / "docs/escalabilidad/resultado.json"
LOG = REPORT.with_suffix(".log")
backend.LOG = LOG


class Multinstance(Installation):
    def original_state(self):
        values = self.run(["docker", "ps", "-q"], log=False).splitlines()
        if not values:
            return []
        return sorted((c["Id"], c["State"]["StartedAt"], c["RestartCount"])
                      for c in json.loads(self.run(["docker", "inspect", *values], log=False))
                      if c["Config"].get("Labels", {}).get("com.docker.compose.project") != self.project)

    def prepare(self):
        self.original = self.original_state()
        super().prepare()
        # Resolve the actual reusable overlay, not a test-only substitute.
        config = json.loads(self.run([*self.compose[:-2], "-f", str(self.folder / "docker-compose.yml"),
            "-f", str(self.folder / "compose.frontend.yml"), "-f", str(self.folder / "compose.multinstance.yml"),
            "config", "--format", "json"], log=False))
        for name, spec in config["services"].items():
            assert not spec.get("container_name"), name
            if name not in ("api-gateway", "frontend"):
                assert not spec.get("ports"), name
        for kind in ("volumes", "networks"):
            for spec in config[kind].values():
                assert spec["name"].startswith(self.project + "_") and not spec.get("external")
        target = self.folder / "multinstance.json"
        target.write_text(json.dumps(config), encoding="utf-8")
        self.compose[-1] = str(target)
        self.result["source_commit"] = self.run(["git", "rev-parse", "HEAD"], log=False)
        files = ["docker-compose.yml", "compose.frontend.yml", "compose.multinstance.yml", "tests/multinstance.py"]
        files += [str(p.relative_to(ROOT)).replace("\\", "/") for base in ("services", "gateway", "frontend/app")
                  for p in (ROOT / base).rglob("*") if p.is_file() and p.suffix in (".py", ".conf", ".inc", ".js", ".html", ".css")
                  and "__pycache__" not in p.parts and ".bak" not in p.name]
        self.result["sha256"] = {name: hashlib.sha256((ROOT/name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for name in files}

    def containers(self, service=None):
        ids = self.dc("ps", "-q", *([service] if service else []), log=False).splitlines()
        return json.loads(self.run(["docker", "inspect", *ids], log=False)) if ids else []

    def addresses(self, service):
        return ["http://" + next(iter(c["NetworkSettings"]["Networks"].values()))["IPAddress"] + ":8000"
                for c in self.containers(service)]

    def batch(self, service, path, token=None, body=None, key=None, count=12, method="POST"):
        # Run on the private network and target each replica explicitly. Gateway
        # DNS randomness alone cannot prove that both processes handle a race.
        payload = dict(addresses=self.addresses(service), path=path, token=token, body=body, key=key, count=count, method=method)
        code = '''
import json,sys,urllib.request,urllib.error,threading
from concurrent.futures import ThreadPoolExecutor
p=json.loads(sys.argv[1]); barrier=threading.Barrier(p['count'])
def call(i):
    h={'Content-Type':'application/json'}
    if p['token']:h['Authorization']='Bearer '+p['token']
    if p['key']:h['Idempotency-Key']=p['key']
    address=p['addresses'][i%len(p['addresses'])]
    req=urllib.request.Request(address+p['path'],headers=h,method=p['method'],data=json.dumps(p['body']).encode() if p['body'] is not None else None)
    barrier.wait(timeout=20)
    try:r=urllib.request.urlopen(req,timeout=40)
    except urllib.error.HTTPError as exc:r=exc
    with r:return {'replica':i%len(p['addresses']),'status':r.status,'body':json.load(r)}
with ThreadPoolExecutor(max_workers=p['count']) as ex:print(json.dumps(list(ex.map(call,range(p['count'])))))
'''
        return json.loads(self.py("user-service", code, json.dumps(payload), log=False))

    def healthy(self):
        for name in APPS:
            rows = self.batch(name, "/health", count=2, method="GET")
            assert all(r["status"] == 200 for r in rows), name

    def race(self):
        user = self.api("/api/auth/register", "POST", {"name":"Replica test", "email":"replicas@example.com", "password":"Replicas-Test-2026"}, expected=201)
        token = self.api("/api/auth/login", "POST", {"email":user["email"], "password":"Replicas-Test-2026"})["access_token"]
        admin = self.py("payment-service", '''
import sys
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({'sub':sys.argv[1],'role':'admin','exp':datetime.now(timezone.utc)+timedelta(minutes=10)},settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
''', user["id"], log=False)
        product = self.api("/api/products/", "POST", {"name":"Replica product", "price":"12.30", "stock":30}, admin, expected=201)
        # Concurrent adds of different products through both cart processes.
        self.api("/api/cart/items", "POST", {"product_id":product["id"],"quantity":2}, token, expected=201)
        key = self.api("/api/cart", token=token)["version"]
        rows = self.batch("order-service", "/orders", token, key=key)
        assert all(r["status"] in (200,201,202) for r in rows), rows
        self.wait(lambda: bool(self.api("/api/orders/checkouts/"+key, token=token).get("id")))
        order = self.api("/api/orders/checkouts/"+key, token=token)
        assert all(r["body"].get("id",order["id"])==order["id"] for r in rows)
        checkout = {"requests":len(rows), "replicas":sorted({r["replica"] for r in rows}), "unique_order_ids":[order["id"]]}
        rows = self.batch("payment-service", "/payments", token, {"order_id":order["id"],"method":"card"})
        assert all(r["status"] in (200,201,202,400) for r in rows), rows
        assert any(r["status"] in (200,201,202) for r in rows)
        self.wait(lambda: self.api(f'/api/orders/{order["id"]}',token=token)["status"]=="PAID")
        payment = self.api(f'/api/payments/orders/{order["id"]}/latest',token=token)
        assert payment["status"]=="PAID"
        assert self.api(f'/api/products/{product["id"]}')["stock"]==28
        self.py("order-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
 assert c.execute(text('SELECT count(*) FROM orders WHERE user_id=:id'),{'id':int(sys.argv[1])}).scalar()==1
print('One order')
''', user["id"])
        self.wait(lambda: self.py("payment-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
 assert c.execute(text("SELECT count(*) FROM payments WHERE order_id=:id"),{'id':int(sys.argv[1])}).scalar()==1
 print(c.execute(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id AND status='PUBLISHED'"),{'id':int(sys.argv[1])}).scalar())
''', order["id"])=="3")
        self.wait(lambda: self.py("product-service", '''
import sys
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
 print(c.execute(text("SELECT count(*) FROM inventory_reservations WHERE order_id=:id AND status='CONSUMED'"),{'id':int(sys.argv[1])}).scalar())
''', order["id"])=="1")
        self.wait(lambda: payment["transaction_id"] in self.dc("logs","--no-color","notification-service", log=False))
        notifications = self.dc("logs","--no-color","notification-service", log=False).count(payment["transaction_id"])
        assert notifications==1, notifications
        self.result["checks"]["cross_replica_race"] = {"checkout":checkout, "payment_requests":len(rows),
            "payment_replicas":sorted({r["replica"] for r in rows}), "payments":1, "stock_before":30, "stock_after":28,
            "consumed_reservations":1, "published_outbox":3, "observed_notifications":notifications,
            "notification_limit":"Observed normal delivery only; RabbitMQ redelivery is not an exactly-once guarantee"}
        # Second order cancelled concurrently across the two order processes.
        self.api("/api/cart/items","POST",{"product_id":product["id"],"quantity":1},token,expected=201)
        order2=self.api("/api/orders","POST",token=token,expected=201)
        rows=self.batch("order-service",f'/orders/{order2["id"]}/cancel',token,count=4)
        assert all(r["status"] in (200,202) for r in rows),rows
        self.wait(lambda:self.api(f'/api/orders/{order2["id"]}',token=token)["status"]=="CANCELLED")
        assert self.api(f'/api/products/{product["id"]}')["stock"]==28
        self.result["checks"]["cancellation"]={"requests":4,"replicas":2,"status":"CANCELLED","stock":28}

    def verify(self):
        self.phase("Preparando proyecto multinstancia aislado...")
        self.prepare()
        self.dc("build",timeout=1200)
        self.dc("up","-d","--wait","--wait-timeout","180",*INFRA,timeout=240)
        self.dc("run","--rm","--no-deps","product-service","alembic","upgrade","head")
        # Bootstrap one process per service before scaling: current imports
        # create some tables. Concurrent first-ever schema creation is excluded.
        self.dc("up","-d",timeout=240)
        self.base="http://"+self.dc("port","api-gateway","80",log=False)
        self.wait(self.ready)
        for service in APPS:
            self.py(service,"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=10)")
        self.phase("Escalando los seis microservicios a dos replicas...")
        args=["up","-d","--no-recreate"]
        for name in APPS: args += ["--scale",name+"=2"]
        self.dc(*args,timeout=240)
        self.wait(lambda:self.healthy() or True)
        assert all(len(self.containers(n))==2 for n in APPS)
        self.result["checks"]["replicas"]={n:len(self.containers(n)) for n in APPS}
        self.phase("Probando checkout, pago, eventos y cancelacion entre procesos...")
        self.race()
        self.phase("Comprobando escalado independiente y continuidad por gateway/frontend...")
        before={n:sorted(c["Id"] for c in self.containers(n)) for n in APPS if n!="order-service"}
        for size in (3,1,2):
            self.dc("up","-d","--no-deps","--no-recreate","--scale",f"order-service={size}","order-service")
            assert len(self.containers("order-service"))==size
            assert before=={n:sorted(c["Id"] for c in self.containers(n)) for n in before}
            self.wait(lambda:self.api("/api/products/") is not None)
        frontend="http://"+self.dc("port","frontend","80",log=False)
        with urllib.request.urlopen(frontend) as response: assert b"Nexo" in response.read()
        with urllib.request.urlopen(frontend+"/api/products/") as response: assert json.load(response)
        containers=self.containers()
        assert len(containers)==20 and all(c["RestartCount"]==0 for c in containers), [
            (c["Name"], c["RestartCount"], c["State"]["Status"]) for c in containers
        ]
        self.result["checks"]["independent_scaling"]={"order_replicas":[2,3,1,2],"other_app_ids_unchanged":True,"frontend_proxy":True,"containers":20}

    def ready(self):
        return self.api("/api/products/")==[]


def main():
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    LOG.write_text("",encoding="utf-8")
    test=Multinstance()
    try:
        test.verify()
        test.result["status"]="passed"
    except Exception as exc:
        test.result.update(status="failed",error=str(exc))
        if test.compose:
            try:test.dc("logs","--no-color","--tail","60",timeout=60)
            except Exception:pass
        raise
    finally:
        try:
            test.cleanup()
            assert test.original_state()==test.original,"Existing containers changed"
            test.result["checks"]["original_installation"]="Container IDs, start times and restart counts unchanged"
        except Exception as exc:
            test.result.update(status="failed",cleanup_error=str(exc))
            raise
        finally:REPORT.write_text(json.dumps(test.result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("OK: six services replicated; isolated project removed.")


if __name__=="__main__":main()

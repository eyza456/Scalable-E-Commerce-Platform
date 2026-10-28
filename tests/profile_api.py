"""Perfilado diagnostico aislado a 20 usuarios; no sustituye aceptacion de 60s."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from performance_load import Performance, ROOT

OUT = ROOT / "docs/perfilado"


class Profile(Performance):
    def __init__(self, label):
        goals = json.loads((ROOT / "tests/performance_goals.json").read_text())
        goals.update({"concurrency": [20], "stage_seconds": 30, "warmup_seconds": 5})
        super().__init__(goals)
        self.label = label
        self.result["mode"] = "profiling-only-not-acceptance"
        self.result["instrument_sha256"] = hashlib.sha256((ROOT / "tests/profile_instrument.py").read_bytes()).hexdigest()

    def note(self, message):
        for value in self.hidden:
            message = message.replace(value, "<redacted>")
        with (OUT / f"{self.label}.log").open("a", encoding="utf-8") as log:
            log.write(message + "\n")

    def prepare(self):
        super().prepare()
        for service in ("order-service", "payment-service", "product-service", "cart-service"):
            app = self.folder / "services" / service / "app"
            shutil.copy2(ROOT / "tests/profile_instrument.py", app / "profile_instrument.py")
            main = app / "main.py"
            source = main.read_text(encoding="utf-8")
            source += "\nfrom app.profile_instrument import install as install_profile\n"
            source += "profile_engine = None\n" if service == "cart-service" else "from app.database import engine as profile_engine\n"
            source += f"install_profile(app, profile_engine, '{service}')\n"
            main.write_text(source, encoding="utf-8")

    def exercise(self):
        super().exercise()
        self.result["status"] = "profile-recorded"
        plans = self.py("order-service", '''
import json
from sqlalchemy import text
from app.database import engine
with engine.connect() as c:
    user=c.execute(text("SELECT user_id FROM orders GROUP BY user_id ORDER BY count(*) DESC LIMIT 1")).scalar()
    plans={}
    for name,extra in [('history',''),('history_paid'," AND status='PAID'")]:
        plans[name]=c.execute(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT * FROM orders WHERE user_id=:id"+extra+" ORDER BY created_at DESC,id DESC LIMIT 20"),{'id':user}).scalar()
    plans['order_items']=c.execute(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT * FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE user_id=:id ORDER BY created_at DESC,id DESC LIMIT 20)"),{'id':user}).scalar()
    print(json.dumps(plans))
''', log=False)
        (OUT / f"{self.label}-planes.json").write_text(plans, encoding="utf-8")
        records = []
        for service in ("order-service", "payment-service", "product-service", "cart-service"):
            log = self.dc("logs", "--no-color", service, log=False)
            for line in log.splitlines():
                if "PERF_PROFILE " in line:
                    try:
                        records.append(json.loads(line.split("PERF_PROFILE ", 1)[1]))
                    except ValueError:
                        pass
        assert records and any(r["path"] == "/orders" and r["method"] == "GET" for r in records)
        (OUT / f"{self.label}-requests.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", choices=("antes", "despues"), required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.label}.log").write_text("", encoding="utf-8")
    test = Profile(args.label)
    try:
        test.verify()
    except Exception as exc:
        test.result["status"], test.result["error"] = "failed", str(exc)
        if test.compose:
            test.dc("logs", "--no-color", "--tail", "50", timeout=60)
        raise
    finally:
        try:
            test.cleanup()
        finally:
            (OUT / f"{args.label}.json").write_text(json.dumps(test.result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Perfil diagnostico guardado:", args.label)


if __name__ == "__main__":
    main()

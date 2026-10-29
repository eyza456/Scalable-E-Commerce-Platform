"""Fresh backend + frontend, random ports/credentials and a real UI journey.

Extends the existing backend installer without changing its historical protocol.
Requires Docker, Python, Node/Playwright/Edge and the locked axe test dependency.
"""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.error
import urllib.request

import fresh_install as backend
from fresh_install import Installation, ROOT, INFRA, APPS

REPORT = ROOT / "docs/frontend/instalacion-desde-cero.json"
LOG = REPORT.with_suffix(".log")
ARTIFACTS = ROOT / "docs/frontend/instalacion-cero"
backend.LOG = LOG


def sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class FrontendInstallation(Installation):
    def original_state(self):
        ids = self.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"),
                        "-f", str(ROOT / "compose.frontend.yml"), "ps", "-q"], log=False).splitlines()
        if not ids:
            return []
        values = json.loads(self.run(["docker", "inspect", *ids], log=False))
        return sorted((value["Id"], value["State"]["StartedAt"], value["RestartCount"]) for value in values)

    def prepare(self):
        super().prepare()
        prefix = self.compose[:-2]
        resolved = self.run([*self.compose, "-f", str(self.folder / "compose.frontend.yml"),
                             "config", "--format", "json"], log=False)
        config = json.loads(resolved)
        assert "frontend" in config["services"]
        frontend = config["services"]["frontend"]
        frontend.pop("container_name", None)
        frontend["ports"] = [{"target": 80, "published": "0", "host_ip": "127.0.0.1", "protocol": "tcp"}]
        for name, spec in config["services"].items():
            assert "container_name" not in spec, name
            if name not in ("frontend", "api-gateway"):
                assert not spec.get("ports"), name
        for kind in ("volumes", "networks"):
            for spec in config[kind].values():
                assert spec["name"].startswith(self.project + "_") and not spec.get("external")
        isolated = self.folder / "with-frontend.json"
        isolated.write_text(json.dumps(config), encoding="utf-8")
        self.compose = [*prefix, "-f", str(isolated)]
        self.dc("config", "--quiet")
        self.result["checks"]["frontend_configuration"] = "Actual frontend overlay; isolated project, network and loopback random port"
        self.result["source_commit"] = self.run(["git", "rev-parse", "HEAD"], log=False)
        self.result["source_note"] = "Tracked working-tree bytes copied at preparation; hashes identify exact sources, including staged edits"
        sources = ["README.md", "frontend/README.md", ".env.example", "docker-compose.yml", "compose.frontend.yml",
                   "frontend/Dockerfile", "frontend/nginx.conf", "tests/fresh_install.py", "tests/smoke_purchase.py",
                   "tests/frontend_journey.cjs", "tests/browser-tools/package-lock.json"]
        sources += [str(p.relative_to(self.folder)).replace("\\", "/") for p in (self.folder / "frontend/app").glob("*") if p.is_file()]
        self.result["sha256"] = {name: sha(self.folder / name) for name in sources}
        self.result["runner_sha256"] = sha(__file__)

    def frontend_get(self, path, expected=200):
        try:
            response = urllib.request.urlopen(self.frontend_base + path, timeout=15)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            body = response.read()
            assert response.status == expected, f"Frontend {path}: HTTP {response.status}, expected {expected}"
            return body

    def browser(self):
        self.phase("Ejecutando recorrido visual y auditorias sobre el frontend nuevo...")
        runtime = shutil.which("node")
        assert runtime, "Node.js es necesario para Playwright"
        axe = ROOT / "tests/browser-tools/node_modules/axe-core"
        assert axe.is_dir(), "Ejecutar npm ci --prefix tests/browser-tools --ignore-scripts"
        assert json.loads((axe / "package.json").read_text())["version"] == "4.14.0"
        self.env["TEST_COMPOSE_ARGS"] = json.dumps(self.compose)
        self.env["FRONTEND_URL"] = self.frontend_base + "/"
        self.env["AXE_CORE_MODULE"] = str(axe)
        command = [runtime, str(self.folder / "tests/frontend_journey.cjs")]
        proc = subprocess.run(command, cwd=self.folder, env=self.env, text=True,
                              encoding="utf-8", errors="replace", capture_output=True, timeout=600)
        self.note(proc.stdout + proc.stderr)
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        path = self.folder / "docs/frontend/recorrido-accesibilidad.json"
        if path.exists():
            shutil.copy2(path, ARTIFACTS / "recorrido-accesibilidad.json")
        for name in ("carrito-desktop.png", "pago-aprobado.png", "catalogo-mobile.png", "historial-mobile.png"):
            image = self.folder / "docs/frontend/demo" / name
            if image.exists():
                shutil.copy2(image, ARTIFACTS / name)
        assert proc.returncode == 0, "Fallo del recorrido visual; revisar log y artefactos de la instalacion"
        result = json.loads(path.read_text(encoding="utf-8"))
        assert result["status"] == "passed" and result["cleanup"]
        assert len(result["steps"]) == 9 and len(result["audits"]) == 14
        assert all(not audit["violations"] and not audit["incomplete"] for audit in result["audits"])
        assert all(value["fits"] for value in result["layouts"])
        for name, digest in result["sha256"].items():
            assert sha(self.folder / name) == digest, name
        self.result["checks"]["browser"] = {"status": "passed", "steps": 9, "audits": 14,
            "violations": 0, "incomplete": 0, "reflow_checks": len(result["layouts"]),
            "fixtures_cleaned": True, "report": "instalacion-cero/recorrido-accesibilidad.json"}

    def verify(self):
        node = shutil.which("node")
        assert node, "Node.js requerido"
        self.run([node, "-e", "require('playwright'); require('./tests/browser-tools/node_modules/axe-core')"], log=False, timeout=30)
        self.original = self.original_state()
        self.phase("Preparando instalacion aislada del backend y frontend...")
        self.prepare()
        self.result["host"] = {"system": platform.system(), "python": platform.python_version(),
            "node": self.run([node, "--version"], log=False),
            "compose": self.run(["docker", "compose", "version", "--short"], log=False),
            "docker": self.run(["docker", "version", "--format", "{{.Server.Version}}"], log=False)}
        self.phase("Construyendo las ocho imagenes de aplicaciones, gateway y frontend...")
        self.dc("build", timeout=1200)
        self.phase("Arrancando infraestructura con volumenes nuevos...")
        self.dc("up", "-d", "--wait", "--wait-timeout", "180", *INFRA, timeout=240)
        self.phase("Aplicando y repitiendo migraciones Alembic antes del arranque...")
        for _ in range(2):
            self.dc("run", "--rm", "--no-deps", "product-service", "alembic", "upgrade", "head")
        assert "b1c5a09e3d72 (head)" in self.dc("run", "--rm", "--no-deps", "product-service", "alembic", "current")
        self.result["checks"]["alembic"] = "b1c5a09e3d72 (head); upgrade repeated"
        self.phase("Arrancando y comprobando las aplicaciones y el frontend...")
        self.dc("up", "-d", timeout=240)
        self.base = "http://" + self.dc("port", "api-gateway", "80", log=False)
        self.frontend_base = "http://" + self.dc("port", "frontend", "80", log=False)
        for service in APPS:
            self.py(service, '''
import json,time,urllib.request
deadline=time.monotonic()+90
while True:
 try:
  with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3) as r:assert json.load(r)['status']=='healthy'
  break
 except Exception:
  if time.monotonic()>deadline:raise
  time.sleep(1)
print('Health OK')
''')
        self.wait(lambda: self.api("/health")["status"] == "healthy")
        self.wait(lambda: json.loads(self.frontend_get("/health"))["status"] == "healthy")
        self.dc("exec", "-T", "frontend", "nginx", "-t")
        for name in ("/", "/styles.css", "/app.js", "/commerce.js", "/payments.js", "/orders.js", "/profile.js"):
            assert self.frontend_get(name), name
        for name in ("/.env", "/stitch/catalogo.html", "/api/orders/internal/test"):
            self.frontend_get(name, 404)
        self.frontend_get("/api/users/me", 401)
        assert json.loads(self.frontend_get("/api/products/")) == []
        ids = self.dc("ps", "-a", "-q", log=False).splitlines()
        containers = json.loads(self.run(["docker", "inspect", *ids], log=False))
        assert len(containers) == 14 and all(c["State"]["Running"] and c["RestartCount"] == 0 for c in containers)
        self.result["checks"]["initial_start"] = "14 running containers; zero unexpected restarts"
        self.result["checks"]["frontend"] = "HTML/assets/proxy/auth/internal-route protection checked; empty catalog"
        self.check_schema()
        self.phase("Probando compra y persistencia del stack nuevo ante reinicio...")
        self.exercise()
        self.frontend_base = "http://" + self.dc("port", "frontend", "80", log=False)
        self.wait(lambda: json.loads(self.frontend_get("/health"))["status"] == "healthy")
        assert b"Nexo" in self.frontend_get("/")
        self.browser()


def main():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    test = FrontendInstallation()
    try:
        test.verify()
        test.result["status"] = "passed"
    except Exception as exc:
        test.result["status"] = "failed"
        test.result["error"] = str(exc)
        if test.compose:
            try:
                test.dc("logs", "--no-color", "--tail", "60", timeout=60)
            except Exception:
                pass
        raise
    finally:
        try:
            test.cleanup()
            if hasattr(test, "original"):
                assert test.original_state() == test.original, "La instalacion habitual cambio durante la prueba"
                test.result["checks"]["original_installation"] = "Original IDs, start times and restart counts unchanged"
        except Exception as exc:
            test.result["status"] = "failed"
            test.result["cleanup_error"] = str(exc)
            raise
        finally:
            REPORT.write_text(json.dumps(test.result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK: instalacion limpia completa, persistencia y recorrido UI; proyecto aislado eliminado.")


if __name__ == "__main__":
    main()

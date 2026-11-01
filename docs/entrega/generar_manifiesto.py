"""Build a portable integrity manifest after regenerating the delivery matrices."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/entrega/manifiesto-entrega.json"
TEXT = {".py", ".cjs", ".js", ".css", ".html", ".md", ".json", ".jsonl", ".csv", ".yml", ".yaml", ".txt", ".ini", ".toml", ".ps1", ".sql", ".svg", ".conf", ".inc", ".sh", ".mako"}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def normalized(path, data):
    is_text = path.suffix in TEXT or path.name in ("Dockerfile", ".dockerignore", ".env.example")
    return data.replace(b"\r\n", b"\n") if is_text else data


def main():
    rows = json.loads((ROOT / "docs/auditoria/matriz-requisitos.json").read_text(encoding="utf-8"))
    assert len(rows) == 78 and len({r["id"] for r in rows}) == 78
    counts = Counter(r["status"] for r in rows)
    assert counts == {"Cumplido": 74, "Parcial": 4}
    suite = json.loads((ROOT / "docs/auditoria/resultado-suite.json").read_text(encoding="utf-8"))
    assert suite["unittest_total"] == 164 and suite["observed_exit_code"] == 0
    assert suite["asgi_import_checks"] == 6
    log = ROOT / "docs/auditoria" / suite["log"]
    assert hashlib.sha256(log.read_bytes()).hexdigest() == suite["log_sha256"]
    ui = json.loads((ROOT / "docs/auditoria/resultado-frontend.json").read_text(encoding="utf-8"))
    assert ui["scenarios"] == 56
    install = json.loads((ROOT / "docs/frontend/instalacion-desde-cero.json").read_text(encoding="utf-8"))
    BASE = install["source_commit"]
    assert install["status"] == "passed" and install["cleanup"]
    journey = json.loads((ROOT / "docs/frontend/recorrido-accesibilidad.json").read_text(encoding="utf-8"))
    assert journey["status"] == "passed" and journey["cleanup"] and len(journey["steps"]) == 9
    assert len(journey["audits"]) == 14 and all(not a["violations"] and not a["incomplete"] for a in journey["audits"])
    assert install["checks"]["initial_start"].startswith("14 ") and install["checks"]["browser"]["audits"] == 14
    for report in ("resultado.json", "independencia.json", "carga/resultado.json"):
        scaling = json.loads((ROOT / "docs/escalabilidad" / report).read_text(encoding="utf-8"))
        assert scaling["status"] == "passed" and scaling["cleanup"], report
        assert len(scaling["checks"]["replicas"]) == 6 and set(scaling["checks"]["replicas"].values()) == {2}
        for name, digest in scaling["sha256"].items():
            assert hashlib.sha256((ROOT/name).read_bytes().replace(b"\r\n",b"\n")).hexdigest() == digest, name
    assert len(json.loads((ROOT / "docs/escalabilidad/independencia.json").read_text())["checks"]["all_services_independent_scaling"]) == 6
    assert scaling["evaluation"]["passed"] and scaling["invariants"]["passed"]
    assert scaling["goals_file_sha256"] == hashlib.sha256((ROOT/"tests/performance_goals.json").read_bytes()).hexdigest()
    initial = json.loads((ROOT/"docs/escalabilidad/carga/inicial/resultado.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((ROOT/"docs/escalabilidad/carga/inicial/instrumento.py").read_bytes().replace(b"\r\n",b"\n")).hexdigest() == initial["sha256"]["tests/multinstance_load.py"]
    for name, digest in install["sha256"].items():
        historical = git("show", f"{BASE}:{name}").replace(b"\r\n", b"\n")
        assert hashlib.sha256(historical).hexdigest() == digest, name
    assert hashlib.sha256(git("show", f"{BASE}:tests/frontend_fresh_install.py").replace(b"\r\n", b"\n")).hexdigest() == install["runner_sha256"]
    tracked = git("ls-files").decode("utf-8").splitlines()
    runtime = [name for name in tracked if name.startswith(("services/", "gateway/", "frontend/app/", "k8s/", "scripts/"))
               or name in ("docker-compose.yml", "compose.frontend.yml", "compose.tls.yml", "frontend/Dockerfile", "frontend/nginx.conf", "frontend/.dockerignore", ".env.example")]
    for name in runtime:
        assert normalized(Path(name), (ROOT/name).read_bytes()) == normalized(Path(name), git("show", f"{BASE}:{name}")), name
    artifacts = [name for name in tracked if name in ("README.md", "frontend/README.md", "tests/run_stability.ps1", "compose.multinstance.yml", "docs/modularidad.md")
        or name.startswith("tests/") and Path(name).suffix in (".py", ".cjs", ".json")
        or name.startswith("docs/entrega/") and Path(name).suffix in (".md", ".py", ".json")
        or name.startswith("docs/frontend/") and Path(name).suffix in (".md", ".json", ".png")
        or name.startswith("docs/escalabilidad/") and Path(name).suffix in (".md", ".py", ".json", ".jsonl")
        or name.startswith("docs/auditoria/") and "/historico-" not in name and Path(name).suffix in (".md", ".json", ".csv", ".py")
        or name in ("docs/rendimiento/informe.md", "docs/rendimiento/resultado.json", "docs/rendimiento/evidencias.json")]
    entries = {}
    for name in sorted(set(runtime + artifacts) - {OUT.relative_to(ROOT).as_posix()}):
        path = ROOT/name
        data = normalized(path, path.read_bytes())
        assert path.name != ".env" and "node_modules" not in path.parts
        entries[name] = {"sha256": hashlib.sha256(data).hexdigest(), "canonical_bytes": len(data)}
    historical_tag = git("rev-parse", "v0.1.0-rc.1^{}").decode().strip()
    assert historical_tag == "d92380e505fd050be4483f3896aa1643c39f4e6c", "La etiqueta historica cambio"
    value = {"generated_at": datetime.now(timezone.utc).isoformat(), "runtime_reference_commit": git("rev-parse", BASE).decode().strip(),
        "runtime_matches_reference": True, "additional_deployment_profiles": ["compose.multinstance.yml"],
        "documentation_review_base": git("rev-parse", "HEAD").decode().strip(),
        "historical_tag": {"name": "v0.1.0-rc.1", "commit": historical_tag, "moved": False},
        "configured_remotes": git("remote").decode().splitlines(),
        "requirements": {"total": 78, "fulfilled": counts["Cumplido"], "partial": counts["Parcial"], "pending": 0},
        "validation": {"backend_unittest": 164, "asgi_import_safe_services": 6, "browser_scenarios": 56, "journey_steps": 9, "automated_audit_states": 14, "fresh_installation_containers": 14,
            "replicated_microservices": 6, "replicas_per_service": 2, "replica_profile_containers": 20,
            "replica_load_goals_passed": len(scaling["evaluation"]["checks"]),
            "replica_load_http_requests": sum(stage["requests"] for stage in scaling["stages"])},
        "normalization": "SHA-256; text CRLF normalized to LF, binary files hashed raw. Manifest excludes itself.",
        "scope": "Local integrated delivery. Core runtime matches reference; additional replica overlay and its executions are verified separately. This manifest does not rerun tests or imply production certification. Execution dates live in the evidence files.",
        "files": entries}
    OUT.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Manifest verified: {len(entries)} files; runtime matches {BASE}.")


if __name__ == "__main__":
    main()

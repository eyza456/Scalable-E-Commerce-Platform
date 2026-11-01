"""Observa continuidad del gateway al detener una replica de catalogo.

Uso con el perfil multinstancia ya iniciado:
  python tests/replica_failover.py --project-name ecommerce-replicas \
      --gateway-url http://127.0.0.1:PORT

El script solo detiene y vuelve a arrancar un contenedor del proyecto indicado;
no elimina volumenes ni cambia la instalacion habitual.
"""

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(compose, *args):
    return subprocess.check_output([*compose, *args], cwd=ROOT, text=True).strip()


def get(url):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def wait_http(url, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if get(url) == 200:
                return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError(f"No responde {url}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--service", default="product-service")
    parser.add_argument("--path", default="/api/products/")
    parser.add_argument("--report", default="docs/escalabilidad/fallo-replica.json")
    args = parser.parse_args()
    compose = [
        "docker", "compose", "--project-name", args.project_name,
        "-f", "docker-compose.yml", "-f", "compose.frontend.yml",
        "-f", "compose.multinstance.yml",
    ]
    containers = [c for c in run(compose, "ps", "-q", args.service).splitlines() if c]
    if len(containers) < 2:
        raise RuntimeError(f"{args.service} requiere al menos dos replicas")
    target = containers[0]
    health = args.gateway_url.rstrip("/") + "/health"
    endpoint = args.gateway_url.rstrip("/") + args.path
    wait_http(health)
    before = [get(endpoint) for _ in range(5)]
    subprocess.check_call(["docker", "stop", target], cwd=ROOT)
    try:
        during = [get(endpoint) for _ in range(10)]
        if any(status != 200 for status in during):
            raise RuntimeError(f"El gateway no mantuvo disponibilidad: {during}")
    finally:
        subprocess.check_call(["docker", "start", target], cwd=ROOT)
    wait_http(health)
    report = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "project": args.project_name,
        "service": args.service,
        "replicas_before": len(containers),
        "stopped_container": target,
        "endpoint": endpoint,
        "before_statuses": before,
        "during_failure_statuses": during,
        "gateway_continuous": all(status == 200 for status in during),
        "recovered": True,
        "scope": "Prueba local de continuidad; no certifica HA de base de datos ni SLA productivo",
    }
    output = ROOT / args.report
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

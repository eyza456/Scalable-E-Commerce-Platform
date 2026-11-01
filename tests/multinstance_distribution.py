"""Observe real gateway distribution across two live application replicas."""
import hashlib
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import urllib.request

import multinstance as multi
from fresh_install import APPS, ROOT, INFRA

REPORT = ROOT / "docs/escalabilidad/distribucion.json"
multi.backend.LOG = REPORT.with_suffix(".log")


class GatewayDistribution(multi.Multinstance):
    def prepare(self):
        super().prepare()
        name = "tests/multinstance_distribution.py"
        self.result["sha256"][name] = hashlib.sha256(
            (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()

    def wait_replicas(self, service):
        self.py("user-service", '''
import json,sys,time,urllib.request
for base in json.loads(sys.argv[1]):
 deadline=time.monotonic()+90
 while True:
  try:
   with urllib.request.urlopen(base+'/health',timeout=3) as r: assert json.load(r)['status']=='healthy'
   break
  except Exception:
   if time.monotonic()>deadline: raise
   time.sleep(1)
''', json.dumps(self.addresses(service)))

    def gateway_logs(self, marker):
        # The nginx image links access.log to /dev/stdout, so reading it with
        # `cat` would wait forever for EOF. Compose logs provides the same
        # records without touching the container's still-open stdout pipe.
        raw = self.dc("logs", "--no-color", "api-gateway", log=False)
        return [line for line in raw.splitlines() if f"probe={marker}" in line]

    def verify(self):
        self.phase("Preparando proyecto multinstancia aislado para observar el gateway...")
        self.prepare()
        self.dc("build", timeout=1200)
        self.dc("up", "-d", "--wait", "--wait-timeout", "180", *INFRA, timeout=240)
        self.dc("run", "--rm", "--no-deps", "product-service", "alembic", "upgrade", "head")
        self.dc("up", "-d", timeout=240)
        self.base = "http://" + self.dc("port", "api-gateway", "80", log=False)
        self.wait(lambda: self.api("/api/products/") == [])
        for service in APPS:
            self.wait_replicas(service)

        self.phase("Escalando los seis microservicios a dos replicas...")
        args = ["up", "-d", "--no-recreate"]
        for name in APPS:
            args += ["--scale", name + "=2"]
        self.dc(*args, timeout=240)
        for service in APPS:
            assert len(self.containers(service)) == 2, service
            self.wait_replicas(service)

        # Let the resolver's short cache expire after the second DNS answer is
        # available. The probe header is logged only for this test and is not
        # forwarded to application clients.
        time.sleep(6)
        marker = "rf49-" + uuid.uuid4().hex
        count = 80

        def request(_):
            req = urllib.request.Request(
                self.base + "/api/products/",
                method="GET",
                headers={"X-RF49-Probe": marker, "Connection": "close"},
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                assert response.status == 200
                response.read()

        self.phase(f"Enviando {count} solicitudes etiquetadas por el gateway...")
        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(request, range(count)))

        lines = []
        deadline = time.monotonic() + 30
        while len(lines) < count and time.monotonic() < deadline:
            lines = self.gateway_logs(marker)
            if len(lines) < count:
                time.sleep(1)
        assert len(lines) == count, f"logs del probe: {len(lines)}/{count}"
        addresses = [re.search(r"upstream_addr=([^ ]+)", line).group(1) for line in lines]
        counts = {address: addresses.count(address) for address in sorted(set(addresses))}
        product = self.containers("product-service")
        ip_to_container = {}
        for container in product:
            network = next(iter(container["NetworkSettings"]["Networks"].values()))
            ip_to_container[network["IPAddress"] + ":8000"] = container["Name"].lstrip("/")
        observed = {address: ip_to_container.get(address, "unknown") for address in counts}
        assert len(counts) == 2, counts
        assert all(value >= 5 for value in counts.values()), counts
        self.result["checks"]["gateway_distribution"] = {
            "service": "product-service",
            "replicas": 2,
            "requests": count,
            "probe_header": "X-RF49-Probe",
            "upstream_counts": counts,
            "upstream_containers": observed,
            "distinct_upstreams": len(counts),
            "all_replicas_observed": len(counts) == 2,
            "minimum_requests_per_replica": min(counts.values()),
        }


def main():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    multi.backend.LOG.write_text("", encoding="utf-8")
    test = GatewayDistribution()
    try:
        test.verify()
        test.result["status"] = "passed"
    except Exception as exc:
        test.result.update(status="failed", error=str(exc))
        if test.compose:
            try:
                test.dc("logs", "--no-color", "--tail", "80", timeout=60)
            except Exception:
                pass
        raise
    finally:
        try:
            test.cleanup()
            assert test.original_state() == test.original, "Existing containers changed"
            test.result["checks"]["original_installation"] = "Container IDs, start times and restart counts unchanged"
        except Exception as exc:
            test.result.update(status="failed", cleanup_error=str(exc))
            raise
        finally:
            REPORT.write_text(json.dumps(test.result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK: gateway distributed requests across both live replicas; isolated project removed.")


if __name__ == "__main__":
    main()

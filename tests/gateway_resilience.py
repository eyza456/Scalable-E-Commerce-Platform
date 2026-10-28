"""Gateway y backend desechables en una red propia; no detiene los servicios reales."""
import json
from pathlib import Path
import subprocess
import time
import unittest
import urllib.error
import urllib.request
import uuid


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, timeout=40).stdout.strip()


class GatewayResilience(unittest.TestCase):
    def test_forwarding_outages_and_backend_ip_change(self):
        prefix = "gateway-test-" + uuid.uuid4().hex
        network, edge, backend, filler = [prefix + suffix for suffix in ("-net", "-edge", "-backend", "-filler")]
        gateway_image = docker("compose", "images", "-q", "api-gateway").splitlines()[0]
        python_image = docker("compose", "images", "-q", "payment-service").splitlines()[0]
        probe = str(Path(__file__).with_name("gateway_probe.py").resolve())
        try:
            docker("network", "create", "--label", "codex.gateway-test=" + prefix, network)
            docker("run", "-d", "--name", edge, "--network", network, "-p", "127.0.0.1::80", gateway_image)
            port = docker("port", edge, "80/tcp").split(":")[-1]
            base = "http://127.0.0.1:" + port

            def exchange(path, method="GET", body=None, headers=None):
                req = urllib.request.Request(base + path, method=method,
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={"Content-Type": "application/json", **(headers or {})})
                try:
                    response = urllib.request.urlopen(req, timeout=8)
                except urllib.error.HTTPError as exc:
                    response = exc
                with response:
                    return response.code, json.load(response), response.headers

            def wait_for(predicate):
                deadline = time.monotonic() + 20
                while True:
                    try:
                        if predicate():
                            return
                    except (OSError, ValueError):
                        pass
                    self.assertLess(time.monotonic(), deadline, "El gateway no se recupero")
                    time.sleep(0.25)

            def start_backend(probe_id):
                docker("run", "-d", "--name", backend, "--network", network,
                    "--network-alias", "cart-service", "-e", "PROBE_ID=" + probe_id,
                    "--mount", f"type=bind,source={probe},target=/probe.py,readonly",
                    "--entrypoint", "python", python_image, "/probe.py")

            wait_for(lambda: exchange("/health")[0] == 200)
            # Arranque independiente: no existe ningun backend en esta red.
            self.assertEqual(exchange("/api/cart")[0], 503)
            self.assertEqual(exchange("/health")[0], 200)
            start_backend("first")
            wait_for(lambda: exchange("/api/cart")[1].get("probe") == "first")
            status, data, headers = exchange("/api/cart/items?search=100%25_%C3%A9", "POST", {"quantity": 2}, {
                "Authorization": "Bearer probe-token",
                "X-Internal-Service-Key": "untrusted-secret",
                "X-Forwarded-For": "untrusted-address",
            })
            self.assertEqual(status, 200)
            self.assertEqual(data["method"], "POST")
            self.assertEqual(data["body"], {"quantity": 2})
            self.assertEqual(data["path"], "/cart/items?search=100%25_%C3%A9")
            forwarded = {name.lower(): value for name, value in data["headers"].items()}
            self.assertEqual(forwarded["authorization"], "Bearer probe-token")
            self.assertNotIn("x-internal-service-key", forwarded)
            self.assertNotEqual(forwarded["x-forwarded-for"], "untrusted-address")
            self.assertEqual(forwarded["x-request-id"], headers["X-Request-ID"])
            # Un 503 generado por la aplicacion conserva su contenido original.
            self.assertEqual(exchange("/api/cart?status=503")[1]["probe"], "first")

            old_ip = json.loads(docker("inspect", backend))[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
            docker("rm", "-f", backend)
            # Ocupar la IP antigua fuerza un cambio real, no una reutilizacion.
            docker("run", "-d", "--name", filler, "--network", network,
                   "--entrypoint", "python", python_image, "-c", "import time; time.sleep(120)")
            start_backend("replacement")
            new_ip = json.loads(docker("inspect", backend))[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
            self.assertNotEqual(old_ip, new_ip)
            wait_for(lambda: exchange("/api/cart")[1].get("probe") == "replacement")
            self.assertEqual(exchange("/health")[0], 200)
        finally:
            for name in (edge, backend, filler):
                assert name.startswith(prefix)
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            subprocess.run(["docker", "network", "rm", network], capture_output=True, timeout=30)


if __name__ == "__main__":
    unittest.main(verbosity=2)

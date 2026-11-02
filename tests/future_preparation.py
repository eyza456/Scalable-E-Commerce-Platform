"""Checks offline for the Kubernetes/TLS/cross-platform preparation artifacts."""

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FuturePreparation(unittest.TestCase):
    def test_kustomize_base_and_tls_overlay_render(self):
        for folder, expected in (("k8s/base", 34), ("k8s/overlays/dev", 35)):
            rendered = subprocess.check_output(
                ["kubectl", "kustomize", folder], cwd=ROOT, text=True
            )
            self.assertEqual(rendered.count("apiVersion:"), expected)
            for name in (
                "user-service", "product-service", "cart-service", "order-service",
                "payment-service", "notification-service", "api-gateway", "frontend",
            ):
                self.assertRegex(rendered, rf"name: {name}\b")
        overlay = subprocess.check_output(
            ["kubectl", "kustomize", "k8s/overlays/dev"], cwd=ROOT, text=True
        )
        self.assertIn("kind: Ingress", overlay)
        self.assertIn("secretName: ecommerce-tls", overlay)
        self.assertNotIn("type: LoadBalancer", overlay)

        production = subprocess.check_output(
            ["kubectl", "kustomize", "k8s/overlays/prod"], cwd=ROOT, text=True
        )
        self.assertEqual(production.count("apiVersion:"), 43)
        self.assertIn("kind: ClusterIssuer", production)
        self.assertIn("server: https://acme-v02.api.letsencrypt.org/directory", production)
        self.assertIn("renewBefore: 720h", production)
        self.assertIn("rotationPolicy: Always", production)
        self.assertNotIn("type: LoadBalancer", production)
        self.assertIn("kind: NetworkPolicy", production)
        self.assertIn("kind: PodDisruptionBudget", production)

    def test_tls_config_has_modern_protocols_and_no_plaintext_proxy(self):
        config = (ROOT / "gateway/nginx.tls.conf").read_text(encoding="utf-8")
        self.assertIn("listen 443 ssl", config)
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3", config)
        self.assertNotRegex(config, r"TLSv1(?:\.0|\.1)\b")
        self.assertIn("Strict-Transport-Security", config)
        self.assertIn("/etc/nginx/tls/tls.crt", config)
        self.assertIn("/etc/nginx/tls/tls.key", config)
        for script in (ROOT / "scripts/generate-dev-cert.ps1", ROOT / "scripts/generate-dev-cert.sh"):
            text = script.read_text(encoding="utf-8")
            self.assertIn("ca.crt", text)
            self.assertIn("serverAuth", text)

        compose_tls = (ROOT / "compose.tls.yml").read_text(encoding="utf-8")
        self.assertIn("TLS_GATEWAY_PORT", compose_tls)
        self.assertNotIn("TLS_HTTP_PORT", compose_tls)

    def test_installation_helpers_cover_windows_and_posix(self):
        powershell = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
        shell = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
        for text in (powershell, shell):
            self.assertIn("docker compose config", text)
            self.assertIn("docker compose build", text)
            self.assertIn("alembic upgrade head", text)
        self.assertTrue((ROOT / "scripts/generate-dev-cert.ps1").is_file())
        self.assertTrue((ROOT / "scripts/generate-dev-cert.sh").is_file())
        self.assertTrue((ROOT / "scripts/apply-prod-tls.ps1").is_file())
        self.assertTrue((ROOT / "scripts/apply-prod-tls.sh").is_file())
        self.assertTrue((ROOT / "scripts/alerts.ps1").is_file())
        self.assertTrue((ROOT / "scripts/alerts.sh").is_file())
        self.assertTrue((ROOT / "scripts/verify-backup.ps1").is_file())
        self.assertTrue((ROOT / "scripts/verify-backup.sh").is_file())
        self.assertTrue((ROOT / "scripts/verify-restore-isolated.ps1").is_file())
        self.assertTrue((ROOT / "scripts/deploy-k8s.ps1").is_file())
        self.assertTrue((ROOT / "tests/replica_failover.py").is_file())

    def test_production_hardening_artifacts(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("redis_data:", compose)
        self.assertIn("rabbitmq_data:", compose)
        self.assertIn('"--appendonly", "yes"', compose)
        for script in (
            ROOT / "scripts/backup.ps1",
            ROOT / "scripts/backup.sh",
            ROOT / "scripts/restore.ps1",
            ROOT / "scripts/restore.sh",
            ROOT / "scripts/monitor.ps1",
            ROOT / "scripts/monitor.sh",
        ):
            self.assertTrue(script.is_file(), script)
        for requirements in ROOT.glob("services/*/requirements.txt"):
            direct = [
                line.strip()
                for line in requirements.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
            self.assertTrue(direct, requirements)
            self.assertTrue(all("==" in line for line in direct), requirements)
        users = (ROOT / "services/user-service/app/routers/users.py").read_text(encoding="utf-8")
        self.assertIn('@router.get("", response_model=list[UserResponse])', users)
        self.assertIn('@router.get("/{user_id}"', users)
        self.assertIn('@router.patch("/{user_id}"', users)
        for main in ROOT.glob("services/*/app/main.py"):
            self.assertIn('"/ready"', main.read_text(encoding="utf-8"))

        admin = (ROOT / "frontend/app/admin.js").read_text(encoding="utf-8")
        admin_html = (ROOT / "frontend/app/index.html").read_text(encoding="utf-8")
        for endpoint in ("/products/", "/categories", "/orders/admin", "/status"):
            self.assertIn(endpoint, admin)
        for panel in ("data-admin-tab=\"products\"", "data-admin-tab=\"categories\"", "data-admin-tab=\"orders\""):
            self.assertIn(panel, admin_html)


if __name__ == "__main__":
    unittest.main(verbosity=2)

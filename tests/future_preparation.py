"""Checks offline for the Kubernetes/TLS/cross-platform preparation artifacts."""

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FuturePreparation(unittest.TestCase):
    def test_kustomize_base_and_tls_overlay_render(self):
        for folder, expected in (("k8s/base", 31), ("k8s/overlays/dev", 32)):
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

    def test_installation_helpers_cover_windows_and_posix(self):
        powershell = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
        shell = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
        for text in (powershell, shell):
            self.assertIn("docker compose config", text)
            self.assertIn("docker compose build", text)
            self.assertIn("alembic upgrade head", text)
        self.assertTrue((ROOT / "scripts/generate-dev-cert.ps1").is_file())
        self.assertTrue((ROOT / "scripts/generate-dev-cert.sh").is_file())
        self.assertTrue((ROOT / "tests/replica_failover.py").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)

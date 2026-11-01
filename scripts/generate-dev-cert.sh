#!/usr/bin/env bash
set -euo pipefail
out="${1:-secrets/tls}"
cn="${2:-localhost}"
mkdir -p "$out"
command -v openssl >/dev/null || { echo "openssl no esta disponible en PATH" >&2; exit 1; }
openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
  -keyout "$out/tls.key" -out "$out/tls.crt" \
  -subj "/CN=$cn" \
  -addext "subjectAltName=DNS:$cn,DNS:localhost,IP:127.0.0.1"
echo "Certificado de desarrollo creado en $out (no usar en produccion)."

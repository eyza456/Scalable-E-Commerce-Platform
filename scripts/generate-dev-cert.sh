#!/usr/bin/env bash
set -euo pipefail
out="${1:-secrets/tls}"
cn="${2:-localhost}"
mkdir -p "$out"
command -v openssl >/dev/null || { echo "openssl no esta disponible en PATH" >&2; exit 1; }
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout "$out/ca.key" -out "$out/ca.crt" \
  -subj "/CN=Ecommerce Development CA" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:1" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
openssl req -new -nodes -newkey rsa:2048 \
  -keyout "$out/tls.key" -out "$out/tls.csr" -subj "/CN=$cn"
cat > "$out/tls.ext" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:$cn,DNS:localhost,IP:127.0.0.1
EOF
openssl x509 -req -in "$out/tls.csr" -CA "$out/ca.crt" -CAkey "$out/ca.key" \
  -CAcreateserial -out "$out/tls.crt" -days 30 -sha256 -extfile "$out/tls.ext"
rm -f "$out/tls.csr" "$out/tls.ext" "$out/tls.crt.srl"
echo "CA local y certificado de desarrollo creados en $out (no usar en produccion)."

#!/usr/bin/env bash
set -euo pipefail
domain="${1:?Uso: $0 dominio email [contexto]}"
email="${2:?Uso: $0 dominio email [contexto]}"
context="${3:-docker-desktop}"
[[ "$domain" != *.example ]] || { echo "El dominio debe ser real, no .example" >&2; exit 1; }
[[ "$email" != *@example.* ]] || { echo "El correo debe ser real, no example" >&2; exit 1; }
kubectl --context "$context" get crd clusterissuers.cert-manager.io --ignore-not-found -o name >/dev/null || {
  echo "cert-manager no esta instalado en el contexto $context" >&2
  exit 1
}
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for file in issuer.yaml certificate.yaml ingress.yaml; do
  sed -e "s/ecommerce\.example\.com/${domain}/g" \
      -e "s/tls-admin@example\.com/${email}/g" \
      "$root/k8s/overlays/prod/$file" | kubectl --context "$context" apply -f -
done
echo "ClusterIssuer, Certificate e Ingress TLS aplicados para $domain."

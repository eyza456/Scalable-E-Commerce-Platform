#!/usr/bin/env bash
set -euo pipefail
registry="${1:?Uso: $0 registry tag [output]}"
tag="${2:?Uso: $0 registry tag [output]}"
output="${3:-k8s/overlays/prod-pinned/kustomization.yaml}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$(dirname "$root/$output")"
{
  echo '# Generado por scripts/pin-images.sh; no editar manualmente.'
  echo 'apiVersion: kustomize.config.k8s.io/v1beta1'
  echo 'kind: Kustomization'
  echo 'resources:'
  echo '  - ../prod'
  echo 'images:'
  for service in user-service product-service cart-service order-service payment-service notification-service api-gateway frontend; do
    reference="$registry/ecommerce/$service:$tag"
    digest="$(docker buildx imagetools inspect "$reference" | awk '/^Digest:/{print $2; exit}')"
    [[ -n "$digest" ]] || { echo "No se pudo consultar $reference" >&2; exit 1; }
    echo "  - name: ecommerce/$service"
    echo "    newName: $registry/ecommerce/$service"
    echo "    digest: $digest"
  done
} > "$root/$output"
echo "Digests fijados en $root/$output"

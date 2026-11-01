#!/usr/bin/env bash
set -euo pipefail
with_frontend=0
if [[ "${1:-}" == "--with-frontend" ]]; then with_frontend=1; fi
docker compose config --quiet
docker compose build
docker compose up -d --wait --wait-timeout 180 user-db product-db order-db payment-db redis rabbitmq
docker compose run --rm --no-deps product-service alembic upgrade head
docker compose up -d
if [[ "$with_frontend" == 1 ]]; then
  docker compose -f docker-compose.yml -f compose.frontend.yml up -d --build frontend
fi
docker compose ps
echo "Instalacion completada. Ejecuta tests/run_stability.ps1 o los scripts de tests desde Python."

param([switch]$WithFrontend)
$ErrorActionPreference = "Stop"
docker compose config --quiet
docker compose build
docker compose up -d --wait --wait-timeout 180 user-db product-db order-db payment-db redis rabbitmq
docker compose run --rm --no-deps product-service alembic upgrade head
docker compose up -d
if ($WithFrontend) { docker compose -f docker-compose.yml -f compose.frontend.yml up -d --build frontend }
docker compose ps
Write-Host "Instalacion completada. Ejecuta tests/run_stability.ps1 para validar la suite."

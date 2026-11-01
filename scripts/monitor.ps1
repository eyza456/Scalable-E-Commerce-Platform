$ErrorActionPreference = "Stop"
Write-Host "== $((Get-Date).ToUniversalTime().ToString('o')) =="
Write-Host "-- RabbitMQ queues --"
docker compose exec -T rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
Write-Host "-- Payment Outbox --"
$dbUser = (docker compose exec -T payment-db printenv POSTGRES_USER).Trim()
$dbName = (docker compose exec -T payment-db printenv POSTGRES_DB).Trim()
docker compose exec -T payment-db psql -U $dbUser -d $dbName -F "|" -Atc "SELECT status, count(*) FROM outbox_events GROUP BY status ORDER BY status"
Write-Host "-- Service readiness --"
foreach ($service in @("user-service", "product-service", "cart-service", "order-service", "payment-service", "notification-service")) {
  $ready = docker compose exec -T $service python -c "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3))))"
  Write-Host "${service}: $ready"
}

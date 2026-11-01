#!/usr/bin/env bash
set -euo pipefail

echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) =="
echo "-- RabbitMQ queues --"
docker compose exec -T rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
echo "-- Payment Outbox --"
db_user="$(docker compose exec -T payment-db printenv POSTGRES_USER | tr -d '\r')"
db_name="$(docker compose exec -T payment-db printenv POSTGRES_DB | tr -d '\r')"
docker compose exec -T payment-db psql -U "$db_user" -d "$db_name" -F '|' -Atc "SELECT status, count(*) FROM outbox_events GROUP BY status ORDER BY status"
echo "-- Service readiness --"
for service in user-service product-service cart-service order-service payment-service notification-service; do
  docker compose exec -T "$service" python -c 'import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=3))))' | sed "s/^/$service: /"
done

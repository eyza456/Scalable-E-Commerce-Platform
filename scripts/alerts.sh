#!/usr/bin/env bash
set -euo pipefail
max_ready="${MAX_READY_MESSAGES:-100}"
max_unacked="${MAX_UNACKED_MESSAGES:-100}"
max_outbox="${MAX_OUTBOX_PENDING:-100}"
max_rejected="${MAX_REDIS_REJECTED_CONNECTIONS:-0}"
violations=()
while read -r name ready unacked; do
  [[ -z "$name" ]] && continue
  (( ready > max_ready )) && violations+=("RabbitMQ $name messages_ready=$ready")
  (( unacked > max_unacked )) && violations+=("RabbitMQ $name unacknowledged=$unacked")
done < <(docker compose exec -T rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged | tail -n +2)
rejected="$(docker compose exec -T redis redis-cli INFO stats | awk -F: '/^rejected_connections:/{print $2}' | tr -d '\r')"
(( rejected > max_rejected )) && violations+=("Redis rejected_connections=$rejected")
db_user="$(docker compose exec -T payment-db printenv POSTGRES_USER | tr -d '\r')"
db_name="$(docker compose exec -T payment-db printenv POSTGRES_DB | tr -d '\r')"
pending="$(docker compose exec -T payment-db psql -U "$db_user" -d "$db_name" -Atc "SELECT count(*) FROM outbox_events WHERE status IN ('PENDING','RETRY');" | tr -d '\r')"
(( pending > max_outbox )) && violations+=("Outbox pending/retry=$pending")
if ((${#violations[@]})); then printf 'ALERT %s\n' "${violations[@]}" >&2; exit 2; fi
echo 'OK RabbitMQ/Redis/Outbox dentro de umbrales.'

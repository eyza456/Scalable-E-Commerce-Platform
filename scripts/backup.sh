#!/usr/bin/env bash
set -euo pipefail

out="${1:-backups}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$out/$stamp"
mkdir -p "$target"

compose=(docker compose)
db_services=(user-db product-db order-db payment-db)
for service in "${db_services[@]}"; do
  id="$("${compose[@]}" ps -q "$service")"
  [ -n "$id" ] || { echo "Servicio no activo: $service" >&2; exit 1; }
  "${compose[@]}" exec -T "$service" sh -lc 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > /tmp/ecommerce.dump'
  docker cp "$id:/tmp/ecommerce.dump" "$target/$service.dump"
  "${compose[@]}" exec -T "$service" rm -f /tmp/ecommerce.dump >/dev/null
done

redis_id="$("${compose[@]}" ps -q redis)"
[ -n "$redis_id" ] || { echo "Redis no activo" >&2; exit 1; }
"${compose[@]}" exec -T redis redis-cli --rdb /tmp/redis.rdb >/dev/null
docker cp "$redis_id:/tmp/redis.rdb" "$target/redis.rdb"
"${compose[@]}" exec -T redis rm -f /tmp/redis.rdb >/dev/null

rabbit_id="$("${compose[@]}" ps -q rabbitmq)"
[ -n "$rabbit_id" ] || { echo "RabbitMQ no activo" >&2; exit 1; }
"${compose[@]}" exec -T rabbitmq rabbitmqctl export_definitions /tmp/rabbitmq-definitions.json >/dev/null
docker cp "$rabbit_id:/tmp/rabbitmq-definitions.json" "$target/rabbitmq-definitions.json"
"${compose[@]}" exec -T rabbitmq sh -lc 'tar -czf /tmp/rabbitmq-mnesia.tgz -C /var/lib/rabbitmq mnesia' >/dev/null
docker cp "$rabbit_id:/tmp/rabbitmq-mnesia.tgz" "$target/rabbitmq-mnesia.tgz"
"${compose[@]}" exec -T rabbitmq rm -f /tmp/rabbitmq-definitions.json /tmp/rabbitmq-mnesia.tgz >/dev/null

sha256sum "$target"/* > "$target/SHA256SUMS"
printf 'Backup creado en %s\n' "$target"

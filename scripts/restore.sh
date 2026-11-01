#!/usr/bin/env bash
set -euo pipefail

backup="${1:-}"
[ -n "$backup" ] && [ -d "$backup" ] || { echo "Uso: $0 BACKUP_DIR --force" >&2; exit 2; }
[ "${2:-}" = "--force" ] || { echo "La restauracion reemplaza datos; confirma con --force" >&2; exit 2; }

compose=(docker compose)
services=(user-service product-service cart-service order-service payment-service notification-service api-gateway)
"${compose[@]}" stop "${services[@]}" >/dev/null
for service in user-db product-db order-db payment-db; do
  id="$("${compose[@]}" ps -q "$service")"
  docker cp "$backup/$service.dump" "$id:/tmp/restore.dump"
  "${compose[@]}" exec -T "$service" sh -lc 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/restore.dump'
  "${compose[@]}" exec -T "$service" rm -f /tmp/restore.dump >/dev/null
done

redis_id="$("${compose[@]}" ps -aq redis)"
docker exec "$redis_id" sh -lc 'rm -rf /data/appendonlydir /data/appendonly.aof* /data/dump.rdb'
docker cp "$backup/redis.rdb" "$redis_id:/data/dump.rdb"
"${compose[@]}" start redis >/dev/null
"${compose[@]}" up -d rabbitmq >/dev/null
rabbit_id="$("${compose[@]}" ps -q rabbitmq)"
docker cp "$backup/rabbitmq-definitions.json" "$rabbit_id:/tmp/rabbitmq-definitions.json"
"${compose[@]}" exec -T rabbitmq rabbitmqctl import_definitions /tmp/rabbitmq-definitions.json >/dev/null
"${compose[@]}" exec -T rabbitmq rm -f /tmp/rabbitmq-definitions.json >/dev/null
if [ -f "$backup/rabbitmq-mnesia.tgz" ]; then
  "${compose[@]}" stop rabbitmq >/dev/null
  rabbit_id="$("${compose[@]}" ps -aq rabbitmq)"
  docker cp "$backup/rabbitmq-mnesia.tgz" "$rabbit_id:/tmp/rabbitmq-mnesia.tgz"
  docker run --rm --volumes-from "$rabbit_id" alpine sh -lc 'rm -rf /var/lib/rabbitmq/mnesia && tar -xzf /tmp/rabbitmq-mnesia.tgz -C /var/lib/rabbitmq && rm -f /tmp/rabbitmq-mnesia.tgz' >/dev/null
  "${compose[@]}" start rabbitmq >/dev/null
fi
"${compose[@]}" up -d "${services[@]}" >/dev/null
printf 'Restauracion completada desde %s\n' "$backup"

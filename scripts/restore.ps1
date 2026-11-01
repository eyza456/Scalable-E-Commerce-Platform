param(
  [Parameter(Mandatory = $true)][string]$BackupDirectory,
  [switch]$Force
)
$ErrorActionPreference = "Stop"
$backup = [IO.Path]::GetFullPath($BackupDirectory)
if (-not (Test-Path -LiteralPath $backup -PathType Container) -or -not $Force) {
  throw "La restauracion reemplaza datos; usa una carpeta valida y -Force"
}

$services = @("user-service", "product-service", "cart-service", "order-service", "payment-service", "notification-service", "api-gateway")
docker compose stop $services | Out-Null
foreach ($service in @("user-db", "product-db", "order-db", "payment-db")) {
  $id = (docker compose ps -q $service).Trim()
  docker cp (Join-Path $backup "$service.dump") "${id}:/tmp/restore.dump"
  docker compose exec -T $service sh -lc 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/restore.dump'
  docker compose exec -T $service rm -f /tmp/restore.dump | Out-Null
}
$redisId = (docker compose ps -aq redis).Trim()
docker exec $redisId sh -lc 'rm -rf /data/appendonlydir /data/appendonly.aof* /data/dump.rdb'
docker cp (Join-Path $backup "redis.rdb") "${redisId}:/data/dump.rdb"
docker compose start redis | Out-Null
docker compose up -d rabbitmq | Out-Null
$rabbitId = (docker compose ps -q rabbitmq).Trim()
docker cp (Join-Path $backup "rabbitmq-definitions.json") "${rabbitId}:/tmp/rabbitmq-definitions.json"
docker compose exec -T rabbitmq rabbitmqctl import_definitions /tmp/rabbitmq-definitions.json | Out-Null
docker compose exec -T rabbitmq rm -f /tmp/rabbitmq-definitions.json | Out-Null
if (Test-Path -LiteralPath (Join-Path $backup "rabbitmq-mnesia.tgz")) {
  docker compose stop rabbitmq | Out-Null
  $rabbitId = (docker compose ps -aq rabbitmq).Trim()
  docker cp (Join-Path $backup "rabbitmq-mnesia.tgz") "${rabbitId}:/tmp/rabbitmq-mnesia.tgz"
  docker run --rm --volumes-from $rabbitId alpine sh -lc 'rm -rf /var/lib/rabbitmq/mnesia && tar -xzf /tmp/rabbitmq-mnesia.tgz -C /var/lib/rabbitmq && rm -f /tmp/rabbitmq-mnesia.tgz' | Out-Null
  docker compose start rabbitmq | Out-Null
}
docker compose up -d $services | Out-Null
Write-Host "Restauracion completada desde $backup"

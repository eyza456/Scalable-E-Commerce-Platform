param([string]$OutputDirectory = "backups")
$ErrorActionPreference = "Stop"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$target = Join-Path ([IO.Path]::GetFullPath($OutputDirectory)) $stamp
New-Item -ItemType Directory -Force -Path $target | Out-Null

$dbServices = @("user-db", "product-db", "order-db", "payment-db")
foreach ($service in $dbServices) {
  $id = (docker compose ps -q $service).Trim()
  if (-not $id) { throw "Servicio no activo: $service" }
  docker compose exec -T $service sh -lc 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > /tmp/ecommerce.dump'
  docker cp "${id}:/tmp/ecommerce.dump" (Join-Path $target "$service.dump")
  docker compose exec -T $service rm -f /tmp/ecommerce.dump | Out-Null
}
$redisId = (docker compose ps -q redis).Trim()
if (-not $redisId) { throw "Redis no activo" }
docker compose exec -T redis redis-cli --rdb /tmp/redis.rdb | Out-Null
docker cp "${redisId}:/tmp/redis.rdb" (Join-Path $target "redis.rdb")
docker compose exec -T redis rm -f /tmp/redis.rdb | Out-Null

$rabbitId = (docker compose ps -q rabbitmq).Trim()
if (-not $rabbitId) { throw "RabbitMQ no activo" }
docker compose exec -T rabbitmq rabbitmqctl export_definitions /tmp/rabbitmq-definitions.json | Out-Null
docker cp "${rabbitId}:/tmp/rabbitmq-definitions.json" (Join-Path $target "rabbitmq-definitions.json")
docker compose exec -T rabbitmq rm -f /tmp/rabbitmq-definitions.json | Out-Null

Get-ChildItem -LiteralPath $target -File | Get-FileHash -Algorithm SHA256 | ForEach-Object {
  "{0} *{1}" -f $_.Hash.ToLowerInvariant(), $_.Path.Substring($target.Length + 1)
} | Set-Content -LiteralPath (Join-Path $target "SHA256SUMS") -Encoding ascii
Write-Host "Backup creado en $target"

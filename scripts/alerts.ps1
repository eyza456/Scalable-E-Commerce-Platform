param(
  [int]$MaxReadyMessages = 100,
  [int]$MaxUnackedMessages = 100,
  [int]$MaxOutboxPending = 100,
  [int]$MaxRedisRejectedConnections = 0
)

$ErrorActionPreference = "Stop"
$violations = [System.Collections.Generic.List[string]]::new()
function Add-Violation([string]$message) { $violations.Add($message) }

$queues = docker compose exec -T rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged --formatter=json | ConvertFrom-Json
foreach ($queue in $queues) {
  if ([int]$queue.messages_ready -gt $MaxReadyMessages) { Add-Violation "RabbitMQ $($queue.name): messages_ready=$($queue.messages_ready)" }
  if ([int]$queue.messages_unacknowledged -gt $MaxUnackedMessages) { Add-Violation "RabbitMQ $($queue.name): unacknowledged=$($queue.messages_unacknowledged)" }
}

$redisInfo = docker compose exec -T redis redis-cli INFO stats
$rejected = (($redisInfo | Select-String '^rejected_connections:').ToString() -split ':')[1]
if ([int]$rejected -gt $MaxRedisRejectedConnections) { Add-Violation "Redis rejected_connections=$rejected" }

$dbUser = (docker compose exec -T payment-db printenv POSTGRES_USER).Trim()
$dbName = (docker compose exec -T payment-db printenv POSTGRES_DB).Trim()
$pending = [int](docker compose exec -T payment-db psql -U $dbUser -d $dbName -Atc "SELECT count(*) FROM outbox_events WHERE status IN ('PENDING','RETRY');").Trim()
if ($pending -gt $MaxOutboxPending) { Add-Violation "Outbox pending/retry=$pending" }

if ($violations.Count) {
  $violations | ForEach-Object { Write-Error "ALERT $_" }
  exit 2
}
Write-Host "OK RabbitMQ/Redis/Outbox dentro de umbrales."

param([Parameter(Mandatory = $true)][string]$BackupDirectory)
$ErrorActionPreference = "Stop"
$backup = [IO.Path]::GetFullPath($BackupDirectory)
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "verify-backup.ps1") -BackupDirectory $backup
$postgresImage = "postgres@sha256:c1b3783309b6499c795eed7c20135a1a4d25cae1b575c3d52c6f536129a1b109"
$stamp = [Guid]::NewGuid().ToString("N").Substring(0, 8)
foreach ($service in @("user-db", "product-db", "order-db", "payment-db")) {
  $name = "restore-check-$service-$stamp"
  try {
    docker run --name $name -d -e POSTGRES_USER=restore -e POSTGRES_PASSWORD=restore -e POSTGRES_DB=restore $postgresImage | Out-Null
    for ($i = 0; $i -lt 60; $i++) {
      docker exec $name pg_isready -U restore -d restore *> $null
      if ($LASTEXITCODE -eq 0) { break }
      Start-Sleep -Seconds 1
    }
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL aislado no estuvo listo: $service" }
    $dump = Join-Path $backup "$service.dump"
    if (-not (Test-Path -LiteralPath $dump -PathType Leaf)) { throw "Falta $service.dump" }
    docker cp $dump "${name}:/tmp/restore.dump" | Out-Null
    docker exec $name pg_restore --clean --if-exists --no-owner -U restore -d restore /tmp/restore.dump | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "pg_restore fallo para $service" }
    Write-Host "Restore PostgreSQL aislado OK: $service"
  } finally { docker rm -f $name *> $null }
}
Get-Content -Raw -LiteralPath (Join-Path $backup "rabbitmq-definitions.json") | ConvertFrom-Json | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $backup "rabbitmq-mnesia.tgz") -PathType Leaf)) { throw "Falta rabbitmq-mnesia.tgz" }
Write-Host "Definiciones RabbitMQ y archivo Mnesia validos. Redis RDB y los dumps PostgreSQL tienen hashes verificados."

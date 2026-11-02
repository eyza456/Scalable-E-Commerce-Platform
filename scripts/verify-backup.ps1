param([Parameter(Mandatory = $true)][string]$BackupDirectory)
$ErrorActionPreference = "Stop"
$backup = [IO.Path]::GetFullPath($BackupDirectory)
$sums = Join-Path $backup "SHA256SUMS"
if (-not (Test-Path -LiteralPath $sums -PathType Leaf)) { throw "Falta SHA256SUMS en $backup" }
$failures = @()
foreach ($line in Get-Content -LiteralPath $sums) {
  if ($line -notmatch '^([0-9A-Fa-f]{64}) \*(.+)$') { continue }
  $expected = $Matches[1].ToLowerInvariant(); $relative = $Matches[2]
  $path = Join-Path $backup $relative
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $failures += "Falta $relative"; continue }
  $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $expected) { $failures += "Hash invalido: $relative" }
}
if ($failures.Count) { $failures | ForEach-Object { Write-Error $_ }; exit 2 }
Write-Host "Backup integro: $backup"

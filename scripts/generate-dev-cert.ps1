param(
  [string]$OutputDirectory = "secrets/tls",
  [string]$CommonName = "localhost"
)
$ErrorActionPreference = "Stop"
$resolved = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolved | Out-Null
$key = Join-Path $resolved "tls.key"
$crt = Join-Path $resolved "tls.crt"
$opensslPath = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $opensslPath -and (Test-Path "C:\Program Files\Git\usr\bin\openssl.exe")) {
  $opensslPath = "C:\Program Files\Git\usr\bin\openssl.exe"
}
if (-not $opensslPath) { throw "openssl no esta disponible en PATH ni en Git for Windows" }
& $opensslPath req -x509 -nodes -newkey rsa:2048 -days 30 `
  -keyout $key -out $crt -subj "/CN=$CommonName" `
  -addext "subjectAltName=DNS:$CommonName,DNS:localhost,IP:127.0.0.1"
Write-Host "Certificado de desarrollo creado en $resolved (no usar en produccion)."

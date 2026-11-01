param(
  [string]$OutputDirectory = "secrets/tls",
  [string]$CommonName = "localhost"
)
$ErrorActionPreference = "Stop"
$resolved = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolved | Out-Null
$key = Join-Path $resolved "tls.key"
$crt = Join-Path $resolved "tls.crt"
$caKey = Join-Path $resolved "ca.key"
$caCrt = Join-Path $resolved "ca.crt"
$csr = Join-Path $resolved "tls.csr"
$ext = Join-Path $resolved "tls.ext"
$opensslPath = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $opensslPath -and (Test-Path "C:\Program Files\Git\usr\bin\openssl.exe")) {
  $opensslPath = "C:\Program Files\Git\usr\bin\openssl.exe"
}
if (-not $opensslPath) { throw "openssl no esta disponible en PATH ni en Git for Windows" }
& $opensslPath req -x509 -nodes -newkey rsa:2048 -days 365 `
  -keyout $caKey -out $caCrt -subj "/CN=Ecommerce Development CA" `
  -addext "basicConstraints=critical,CA:TRUE,pathlen:1" `
  -addext "keyUsage=critical,keyCertSign,cRLSign"
& $opensslPath req -new -nodes -newkey rsa:2048 -keyout $key -out $csr -subj "/CN=$CommonName"
@"
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:$CommonName,DNS:localhost,IP:127.0.0.1
"@ | Set-Content -Path $ext -Encoding ascii
& $opensslPath x509 -req -in $csr -CA $caCrt -CAkey $caKey -CAcreateserial -out $crt -days 30 -sha256 -extfile $ext
Remove-Item -LiteralPath $csr, $ext, "$crt.srl" -Force -ErrorAction SilentlyContinue
Write-Host "CA local y certificado de desarrollo creados en $resolved (no usar en produccion)."

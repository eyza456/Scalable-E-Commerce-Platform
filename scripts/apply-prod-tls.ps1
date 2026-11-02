param(
  [Parameter(Mandatory = $true)][string]$Domain,
  [Parameter(Mandatory = $true)][string]$Email,
  [string]$Context = "docker-desktop"
)

$ErrorActionPreference = "Stop"
if ($Domain -match "\.example$" -or $Email -match "@example\.") {
  throw "Domain y Email deben ser valores reales; no se permiten placeholders example.com."
}
if ($Domain -notmatch "^[A-Za-z0-9.-]+$") { throw "Domain no tiene un formato DNS valido." }
if ($Email -notmatch "^[^@\s]+@[^@\s]+\.[^@\s]+$") { throw "Email no tiene un formato valido." }
$certManagerCrd = & kubectl --context $Context get crd clusterissuers.cert-manager.io --ignore-not-found -o name
if ($LASTEXITCODE -ne 0 -or -not $certManagerCrd) {
  throw "cert-manager no esta instalado en el contexto $Context. Instala sus CRD y controladores antes de aplicar TLS productivo."
}

$root = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$templates = @(
  (Join-Path $root "k8s\overlays\prod\issuer.yaml"),
  (Join-Path $root "k8s\overlays\prod\certificate.yaml"),
  (Join-Path $root "k8s\overlays\prod\ingress.yaml")
)
foreach ($template in $templates) {
  $rendered = (Get-Content -Raw -LiteralPath $template).Replace("ecommerce.example.com", $Domain).Replace("tls-admin@example.com", $Email)
  $rendered | & kubectl --context $Context apply -f -
  if ($LASTEXITCODE -ne 0) { throw "No se pudo aplicar $template." }
}
Write-Host "ClusterIssuer, Certificate e Ingress TLS aplicados para $Domain."

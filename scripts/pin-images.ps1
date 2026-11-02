param(
  [Parameter(Mandatory = $true)][string]$Registry,
  [Parameter(Mandatory = $true)][string]$Tag,
  [string]$Output = "k8s/overlays/prod-pinned/kustomization.yaml"
)

$ErrorActionPreference = "Stop"
$services = @("user-service", "product-service", "cart-service", "order-service", "payment-service", "notification-service", "api-gateway", "frontend")
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("# Generado por scripts/pin-images.ps1; no editar manualmente.")
$lines.Add("apiVersion: kustomize.config.k8s.io/v1beta1")
$lines.Add("kind: Kustomization")
$lines.Add("resources:")
$lines.Add("  - ../prod")
$lines.Add("images:")
foreach ($service in $services) {
  $reference = "$Registry/ecommerce/$service`:$Tag"
  $inspection = docker buildx imagetools inspect $reference 2>$null
  if ($LASTEXITCODE -ne 0) { throw "No se pudo consultar $reference" }
  $digestLine = $inspection | Select-String -Pattern '^Digest:' | Select-Object -First 1
  if (-not $digestLine) { throw "El registro no devolvio digest para $reference" }
  $digest = ($digestLine.ToString() -split '\s+')[1]
  $lines.Add("  - name: ecommerce/$service")
  $lines.Add("    newName: $Registry/ecommerce/$service")
  $lines.Add("    digest: $digest")
}
$path = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null
$lines | Set-Content -LiteralPath $path -Encoding utf8
Write-Host "Digests fijados en $path"

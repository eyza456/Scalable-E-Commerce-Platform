$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    foreach ($service in @('user-service', 'product-service', 'cart-service', 'order-service', 'payment-service', 'notification-service')) {
        Get-Content -LiteralPath (Join-Path $PSScriptRoot 'import_lifecycle.py') -Raw |
            docker compose exec -T $service python -
        if ($LASTEXITCODE -ne 0) { throw "Efectos al importar: $service" }
    }
    $checks = @(
        @('payment-service', 'payment_stability.py'),
        @('payment-service', 'payment_latest.py'),
        @('payment-service', 'http_pool_stability.py'),
        @('order-service', 'http_pool_stability.py'),
        @('cart-service', 'http_pool_stability.py'),
        @('order-service', 'order_stability.py'),
        @('order-service', 'checkout_stability.py'),
        @('cart-service', 'cart_stability.py'),
        @('product-service', 'product_stability.py'),
        @('product-service', 'catalog_stability.py'),
        @('product-service', 'catalog_migration.py'),
        @('user-service', 'user_stability.py'),
        @('user-service', 'profile_stability.py'),
        @('user-service', 'input_limits.py'),
        @('order-service', 'messaging_stability.py'),
        @('product-service', 'messaging_stability.py'),
        @('order-service', 'messaging_broker.py'),
        @('product-service', 'messaging_broker.py')
    )
    foreach ($check in $checks) {
        Get-Content -LiteralPath (Join-Path $PSScriptRoot $check[1]) -Raw |
            docker compose exec -T $check[0] python -
        if ($LASTEXITCODE -ne 0) { throw "Fallo: $($check[0]) / $($check[1])" }
    }
    python -X utf8 tests/smoke_profile.py
    if ($LASTEXITCODE -ne 0) { throw 'Fallo en perfil HTTP' }
    python -X utf8 tests/smoke_catalog.py
    if ($LASTEXITCODE -ne 0) { throw 'Fallo en catalogo HTTP' }
    python -X utf8 tests/smoke_purchase.py
    if ($LASTEXITCODE -ne 0) { throw 'Fallo en compra HTTP' }
    python -X utf8 tests/smoke_inventory.py
    if ($LASTEXITCODE -ne 0) { throw 'Fallo en reservas y recuperacion HTTP' }
    python -X utf8 tests/smoke_orders.py
    if ($LASTEXITCODE -ne 0) { throw 'Fallo en historial y cancelacion HTTP' }
    python -X utf8 tests/smoke_audit_fixes.py
    if ($LASTEXITCODE -ne 0) { throw 'Regresion de hallazgos de auditoria' }
    python -X utf8 tests/smoke_payment_rejections.py
    if ($LASTEXITCODE -ne 0) { throw 'Fallo en rechazos simulados de pago' }
    python -X utf8 tests/demo_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Fallo en demostracion de entrega' }
    docker compose exec -T api-gateway nginx -t
    if ($LASTEXITCODE -ne 0) { throw 'Configuracion de gateway invalida' }
    python -X utf8 tests/gateway_stability.py
    if ($LASTEXITCODE -ne 0) { throw 'Fallo en rutas y compra por gateway' }
    python -X utf8 tests/gateway_resilience.py
    if ($LASTEXITCODE -ne 0) { throw 'Fallo en recuperacion del gateway' }
}
finally {
    Pop-Location
}

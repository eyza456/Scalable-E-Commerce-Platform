param(
    [string]$Context = "docker-desktop",
    [string]$Namespace = "ecommerce"
)

$ErrorActionPreference = "Stop"

function Invoke-Kubectl {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & kubectl --context $Context @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "kubectl fallo: kubectl --context $Context $($Arguments -join ' ')"
    }
}

docker info | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Engine no esta disponible." }
Invoke-Kubectl get nodes

docker compose build
docker compose -f docker-compose.yml -f compose.frontend.yml build frontend

foreach ($name in @("user-service", "product-service", "cart-service", "order-service", "payment-service", "notification-service", "api-gateway", "frontend")) {
    docker tag "ecommerce-microservices-$name`:latest" "ecommerce/$name`:latest"
}

Invoke-Kubectl create namespace $Namespace --dry-run=client --output=yaml | kubectl --context $Context apply -f -

$secretExists = $true
try { Invoke-Kubectl --namespace=$Namespace get secret ecommerce-secrets | Out-Null } catch { $secretExists = $false }
if (-not $secretExists) {
    $userPassword = "u$((New-Guid).Guid.Replace('-', ''))"
    $productPassword = "p$((New-Guid).Guid.Replace('-', ''))"
    $orderPassword = "o$((New-Guid).Guid.Replace('-', ''))"
    $paymentPassword = "m$((New-Guid).Guid.Replace('-', ''))"
    $secretKey = "$((New-Guid).Guid.Replace('-', ''))$((New-Guid).Guid.Replace('-', ''))"
    $internalKey = "$((New-Guid).Guid.Replace('-', ''))$((New-Guid).Guid.Replace('-', ''))"
    $rabbitCookie = "$((New-Guid).Guid.Replace('-', ''))$((New-Guid).Guid.Replace('-', ''))"
    $secretArgs = @(
        "create", "secret", "generic", "ecommerce-secrets", "--namespace", $Namespace,
        "--from-literal=SECRET_KEY=$secretKey",
        "--from-literal=INTERNAL_SERVICE_KEY=$internalKey",
        "--from-literal=RABBITMQ_ERLANG_COOKIE=$rabbitCookie",
        "--from-literal=USER_DB_USER=users", "--from-literal=USER_DB_PASSWORD=$userPassword",
        "--from-literal=PRODUCT_DB_USER=products", "--from-literal=PRODUCT_DB_PASSWORD=$productPassword",
        "--from-literal=ORDER_DB_USER=orders", "--from-literal=ORDER_DB_PASSWORD=$orderPassword",
        "--from-literal=PAYMENT_DB_USER=payments", "--from-literal=PAYMENT_DB_PASSWORD=$paymentPassword",
        "--from-literal=USER_DATABASE_URL=postgresql+psycopg2://users`:$userPassword@user-db:5432/users",
        "--from-literal=PRODUCT_DATABASE_URL=postgresql+psycopg2://products`:$productPassword@product-db:5432/products",
        "--from-literal=ORDER_DATABASE_URL=postgresql+psycopg2://orders`:$orderPassword@order-db:5432/orders",
        "--from-literal=PAYMENT_DATABASE_URL=postgresql+psycopg2://payments`:$paymentPassword@payment-db:5432/payments",
        "--dry-run=client", "--output=yaml"
    )
    $secretYaml = & kubectl --context $Context @secretArgs
    if ($LASTEXITCODE -ne 0) { throw "No se pudo generar ecommerce-secrets." }
    $secretYaml | kubectl --context $Context apply -f -
    if ($LASTEXITCODE -ne 0) { throw "No se pudo aplicar ecommerce-secrets." }
}

Invoke-Kubectl apply -k k8s/base
Invoke-Kubectl --namespace=$Namespace wait --for=condition=complete job/user-migrations job/product-migrations job/order-migrations job/payment-migrations --timeout=180s
foreach ($deployment in @("user-service", "product-service", "cart-service", "order-service", "payment-service", "notification-service", "api-gateway", "frontend")) {
    Invoke-Kubectl --namespace=$Namespace rollout status "deployment/$deployment" --timeout=180s
}
foreach ($statefulSet in @("user-db", "product-db", "order-db", "payment-db", "redis", "rabbitmq")) {
    Invoke-Kubectl --namespace=$Namespace rollout status "statefulset/$statefulSet" --timeout=180s
}
Invoke-Kubectl --namespace=$Namespace get "pods,svc,pvc,jobs"

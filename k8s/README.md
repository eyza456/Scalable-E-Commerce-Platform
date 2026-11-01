# Preparación Kubernetes y TLS

`base/` contiene los recursos reproducibles de la plataforma: namespace,
secret/config de ejemplo, cuatro PostgreSQL con PVC, Redis, RabbitMQ, seis
microservicios, gateway y frontend. Las imágenes `ecommerce/*:latest` deben
construirse y publicarse en un registro accesible por el clúster; el manifiesto
no contiene credenciales reales.

## Validar y aplicar

```powershell
kubectl kustomize k8s/base | kubectl apply --dry-run=client --validate=false -f -
kubectl apply -k k8s/base
kubectl -n ecommerce get pods,svc,statefulset
```

Para un entorno con Ingress y TLS:

```powershell
kubectl -n ecommerce create secret tls ecommerce-tls --cert=secrets/tls/tls.crt --key=secrets/tls/tls.key
kubectl apply -k k8s/overlays/dev
```

El overlay `dev` usa `ecommerce.local`, termina TLS en el Ingress y conserva el
gateway como backend HTTP interno. Para producción se deben sustituir imágenes,
secretos, StorageClasses, políticas de red, PodDisruptionBudgets y certificados
gestionados (por ejemplo cert-manager); estos manifiestos no son una declaración
de alta disponibilidad de PostgreSQL, Redis o RabbitMQ.

## TLS local con Compose

Genera un certificado autofirmado de desarrollo y arranca el gateway TLS:

```powershell
.\scripts\generate-dev-cert.ps1
docker compose -f docker-compose.yml -f compose.tls.yml up -d --build api-gateway
Invoke-WebRequest https://127.0.0.1:8443/health -SkipCertificateCheck
```

En Linux/macOS usa `./scripts/generate-dev-cert.sh` y el mismo override de
Compose. Nunca reutilizar este certificado autofirmado en producción.

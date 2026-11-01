# Preparación futura: Kubernetes, TLS, réplicas y portabilidad

Este bloque prepara los cuatro apartados que siguen fuera de la certificación
productiva. Los artefactos son verificables localmente, pero no declaran un
cluster Kubernetes, una CA pública, alta disponibilidad de datos ni ejecución en
otro sistema operativo.

## RNF-07 — Kubernetes

`k8s/base` contiene Kustomize para namespace, configuración/secretos de ejemplo,
cuatro PostgreSQL con PVC, Redis, RabbitMQ, seis servicios, gateway y frontend.
`k8s/overlays/dev` añade un Ingress TLS para `ecommerce.local`.

```powershell
kubectl kustomize k8s/base | kubectl apply --dry-run=client --validate=false -f -
kubectl apply -k k8s/base
kubectl -n ecommerce get pods,svc,statefulset
```

La validación offline se ejecuta con `python tests/future_preparation.py`. Antes
de un despliegue real hay que publicar las imágenes en un registro, crear
secretos fuera de Git, elegir StorageClass, configurar NetworkPolicies y probar
backup/restore de las bases.

## RNF-15 — HTTPS/TLS

`gateway/nginx.tls.conf` solo permite TLS 1.2/1.3, redirige HTTP a HTTPS y añade
HSTS. `compose.tls.yml` monta el certificado en `/etc/nginx/tls`.

```powershell
.\scripts\generate-dev-cert.ps1
docker compose -f docker-compose.yml -f compose.tls.yml up -d --build api-gateway
Invoke-WebRequest https://127.0.0.1:8443/health -SkipCertificateCheck
```

El certificado es autofirmado y dura 30 días: sirve para desarrollo, no para
usuarios finales. Producción requiere cert-manager/CA confiable, rotación,
políticas de cifrado y validación desde clientes reales.

## RF-49 — fallo de una réplica

Con el perfil multinstancia levantado, `tests/replica_failover.py` detiene una
réplica de Product, consulta el catálogo a través del gateway y la vuelve a
arrancar:

```powershell
python tests/replica_failover.py --project-name ecommerce-replicas `
  --gateway-url http://127.0.0.1:PUERTO
```

El informe exige respuestas HTTP 200 durante la parada y registra la
recuperación. Esto observa continuidad local; no demuestra reparto uniforme,
fallo de base de datos ni un SLA de producción.

## RNF-27 — Linux/macOS

Los instaladores equivalentes son `scripts/install.ps1` y
`scripts/install.sh`. Ambos validan Compose, construyen imágenes, esperan la
infraestructura, ejecutan Alembic y arrancan la plataforma. La prueba actual de
instalación sigue siendo Windows/Docker Linux; el cierre requiere repetir
`tests/frontend_fresh_install.py` en un host Linux y otro macOS, conservando
versiones, salida y resultado.

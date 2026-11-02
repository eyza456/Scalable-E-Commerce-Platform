# Preparación futura: Kubernetes, TLS, réplicas y portabilidad

Este bloque prepara los cuatro apartados que siguen fuera de la certificación
productiva. RNF-07 ya tiene una verificación real en Docker Desktop Kubernetes;
los límites de producción (multi-nodo, HA de datos, emisión pública condicionada
a DNS y otros sistemas operativos) se mantienen explícitos.

## RNF-07 — Kubernetes

`k8s/base` contiene Kustomize para namespace, configuración, cuatro PostgreSQL
con PVC, Redis y RabbitMQ persistentes, jobs de migración, seis servicios,
gateway y frontend. `k8s/overlays/dev` añade un Ingress TLS para
`ecommerce.local`.

```powershell
kubectl kustomize k8s/base | kubectl apply --dry-run=client --validate=false -f -
.\scripts\deploy-k8s.ps1
kubectl --context docker-desktop -n ecommerce get pods,svc,statefulset,pvc,jobs
```

El script construye y etiqueta las ocho imágenes locales, crea un Secret de
desarrollo aleatorio directamente en Kubernetes (si aún no existe), aplica los
manifiestos, espera los cuatro jobs de migración y verifica todos los rollouts.
El Secret no se guarda en Git. La ejecución validada el 1 de noviembre de 2026
usó el contexto `docker-desktop`, Kubernetes `v1.36.1`, 22 pods `Ready`, cuatro
jobs `Complete` y seis PVC `Bound` con `StorageClass=hostpath`. El gateway
respondió `200` en `/health`, `/api/products/` y `/api/categories`; el frontend
respondió `200` por port-forward.

La validación offline se ejecuta con `python tests/future_preparation.py`. Este
despliegue demuestra operación local de un solo nodo. Antes de producción hay
que publicar imágenes versionadas en un registro, usar un gestor de secretos,
elegir una StorageClass redundante, configurar NetworkPolicies, backup/restore,
monitoreo y un clúster multi-nodo.

## RNF-15 — HTTPS/TLS

`gateway/nginx.tls.conf` solo permite TLS 1.2/1.3, redirige HTTP a HTTPS y añade
HSTS. `compose.tls.yml` monta el certificado en `/etc/nginx/tls` y solo publica
el puerto HTTPS; el puerto HTTP queda interno para la redirección y no se expone
directamente. En Kubernetes, ambos overlays mantienen `api-gateway` como
`ClusterIP` y el Ingress fuerza HTTPS. Los helpers generan una CA local
(`ca.crt`) y firman el certificado de desarrollo para poder validarlo sin
desactivar la verificación:

```powershell
.\scripts\generate-dev-cert.ps1
docker compose -f docker-compose.yml -f compose.tls.yml up -d --build api-gateway
Invoke-WebRequest https://127.0.0.1:8443/health -SkipCertificateCheck
curl.exe --ssl-no-revoke --cacert secrets/tls/ca.crt https://127.0.0.1:8443/health
```

La CA es local y el certificado de servidor dura 30 días: sirve para desarrollo,
no para usuarios finales. `k8s/overlays/prod` configura cert-manager con Let's
Encrypt ACME, CA pública confiable, renovación 30 días antes y rotación de clave
privada. Aplicarlo requiere instalar cert-manager, usar un dominio público y
completar el correo operativo; el helper es
`scripts/apply-prod-tls.ps1`/`scripts/apply-prod-tls.sh`. La emisión pública no
se puede validar en este clúster local sin DNS e Ingress accesibles desde
Internet.

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

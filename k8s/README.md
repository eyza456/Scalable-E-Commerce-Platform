# Preparación Kubernetes y TLS

`base/` contiene los recursos reproducibles de la plataforma: namespace,
configuración, cuatro PostgreSQL con PVC, Redis y RabbitMQ con PVC, cuatro jobs
de migración, seis microservicios, gateway y frontend. Las imágenes
`ecommerce/*:latest` deben construirse y publicarse en un registro accesible por
el clúster. El secreto de
ejemplo se conserva como referencia, pero no se incluye en la Kustomization para
evitar desplegar contraseñas placeholder por accidente.

## Validar y aplicar

```powershell
kubectl kustomize k8s/base | kubectl apply --dry-run=client --validate=false -f -
kubectl create namespace ecommerce --dry-run=client -o yaml | kubectl apply -f -
# Crear ecommerce-secrets fuera de Git antes de aplicar los workloads.
kubectl apply -k k8s/base
kubectl -n ecommerce get pods,svc,statefulset
```

En Docker Desktop puede ejecutarse directamente
`powershell -File .\scripts\deploy-k8s.ps1` desde la raíz del repositorio.
Construye las imágenes locales, genera el Secret aleatorio si falta, aplica los
jobs de migración y espera todos los rollouts. El gateway detecta el nameserver
del pod y usa el DNS de Kubernetes, por lo que las mismas imágenes funcionan con
Compose y dentro del clúster.

El Secret debe contener `SECRET_KEY`, `INTERNAL_SERVICE_KEY`,
`RABBITMQ_ERLANG_COOKIE`, los cuatro pares `*_DB_USER`/`*_DB_PASSWORD` y las
cuatro URL `*_DATABASE_URL`. En desarrollo puede crearse con
`kubectl create secret generic ... --from-literal=...`; en producción debe
proceder de un gestor de secretos. Nunca aplicar `secret.example.yaml` tal cual.

Para un entorno local con Ingress y TLS:

```powershell
kubectl -n ecommerce create secret tls ecommerce-tls --cert=secrets/tls/tls.crt --key=secrets/tls/tls.key
kubectl apply -k k8s/overlays/dev
```

El overlay `dev` usa `ecommerce.local`, termina TLS en el Ingress y conserva el
gateway como backend HTTP interno. El gateway sigue siendo `ClusterIP`; no se
publica un `LoadBalancer` HTTP directo y el Ingress fuerza HTTPS.

## CA publica y rotacion productiva

`k8s/overlays/prod` configura cert-manager con Let's Encrypt ACME. El recurso
`Certificate` fija 90 dias de duracion, renueva 30 dias antes y rota siempre la
clave privada. Antes de aplicar hay que instalar cert-manager, sustituir el
dominio y el correo de ejemplo por valores reales y apuntar DNS al Ingress:

```powershell
kubectl kustomize k8s/overlays/prod
kubectl apply -k k8s/overlays/prod
```

El helper evita editar manifiestos a mano y rechaza placeholders:

```powershell
.\scripts\apply-prod-tls.ps1 -Domain tienda.midominio.com -Email tls@midominio.com
```

El equivalente POSIX es `bash scripts/apply-prod-tls.sh tienda.midominio.com
tls@midominio.com`. Sustituir ambos valores por los reales. La renovación la ejecuta cert-manager; comprobarla con
`kubectl -n ecommerce describe certificate ecommerce-tls`.

Estos manifiestos requieren un dominio público y un Ingress accesible desde
Internet para el desafío HTTP-01. No se debe usar el certificado autofirmado de
desarrollo en producción.

## TLS local con Compose

Genera un certificado autofirmado de desarrollo y arranca el gateway TLS:

```powershell
.\scripts\generate-dev-cert.ps1
docker compose -f docker-compose.yml -f compose.tls.yml up -d --build api-gateway
Invoke-WebRequest https://127.0.0.1:8443/health -SkipCertificateCheck
```

En Linux/macOS usa `./scripts/generate-dev-cert.sh` y el mismo override de
Compose. Nunca reutilizar este certificado autofirmado en producción.

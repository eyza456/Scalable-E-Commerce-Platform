# TLS productivo con CA publica

Este overlay usa cert-manager con Let's Encrypt ACME. La CA es publica y
confiable para los navegadores; cert-manager renueva el secreto `ecommerce-tls`
30 dias antes de su vencimiento y rota siempre la clave privada.

Antes de aplicarlo:

1. Instalar cert-manager y su CRD en el clúster.
2. Reemplazar `ecommerce.example.com` por un DNS real que apunte al Ingress.
3. Reemplazar `tls-admin@example.com` por un correo operativo real.
4. Abrir solo el Ingress; `api-gateway` permanece `ClusterIP` y no tiene HTTP
   directo publicado.

El overlay también aplica NetworkPolicies de denegación por defecto, permite DNS
y tráfico interno de la aplicación, y crea un PodDisruptionBudget para mantener
al menos una réplica disponible. Las bases de datos conservan `hostpath` en el
clúster local; en producción hay que sustituirlo por una StorageClass CSI
redundante antes de aplicar.

Las imágenes de infraestructura usan digests fijados. Las ocho imágenes propias
deben publicarse en un registro y consumirse con digests inmutables generados por
el pipeline de CI; no usar `latest` fuera del entorno local. El helper genera un
overlay aplicable con esos digests:

```powershell
.\scripts\pin-images.ps1 -Registry registry.example.com -Tag 2026.11.02
kubectl apply -k k8s/overlays/prod-pinned
```

Aplicación:

```powershell
kubectl apply -k k8s/overlays/prod
kubectl -n ecommerce get certificate,secret,ingress
kubectl -n ecommerce describe certificate ecommerce-tls
```

No se debe aplicar este ejemplo con los valores `.example.com`.

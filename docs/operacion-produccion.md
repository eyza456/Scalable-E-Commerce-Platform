# Operación y recuperación

Este documento cubre la preparación local antes de exponer la plataforma. No
sustituye un plan de continuidad probado en infraestructura productiva.

## Persistencia

Compose conserva Redis en `redis_data` con AOF (`everysec`) y RabbitMQ completo
(Mnesia, colas, metadatos y cookie Erlang) en `rabbitmq_data`; el cookie se
inicializa desde el secreto de entorno. PostgreSQL ya usa volúmenes separados por servicio. No usar
`docker compose down -v` salvo que se quiera destruir expresamente los datos.

## Backup

Con el stack activo:

```powershell
.\scripts\backup.ps1
```

En Linux/macOS:

```bash
bash scripts/backup.sh
```

El backup contiene dumps PostgreSQL, un RDB de Redis, definiciones y Mnesia de
RabbitMQ, y `SHA256SUMS`. Guardar la carpeta fuera del host y protegerla con
cifrado y control de acceso.

Verificar una copia sin restaurar sobre el entorno principal:

```powershell
.\scripts\verify-backup.ps1 -BackupDirectory backups\20261102T000000Z
```

Para comprobar restauración PostgreSQL en contenedores efímeros, sin tocar el
stack activo:

```powershell
.\scripts\verify-restore-isolated.ps1 -BackupDirectory backups\20261102T000000Z
```

## Restore

La restauración detiene las aplicaciones y reemplaza datos. Requiere confirmación
explícita:

```powershell
.\scripts\restore.ps1 -BackupDirectory backups\20260101T000000Z -Force
```

```bash
bash scripts/restore.sh backups/20260101T000000Z --force
```

Primero probar en una instalación aislada y comprobar usuarios, catálogo,
carritos, pedidos, pagos, colas y Outbox antes de usarla sobre datos reales.

## Readiness y monitoreo

Cada API expone `/health` para liveness y `/ready` para dependencias:

- User: PostgreSQL.
- Product/Order/Payment: PostgreSQL y RabbitMQ.
- Cart: Redis.
- Notification: RabbitMQ.

Compose usa esos endpoints como healthchecks de las aplicaciones. Para revisar
colas y estados del Outbox:

```powershell
.\scripts\monitor.ps1
```

```bash
bash scripts/monitor.sh
```

En producción, enviar estas métricas a un sistema de monitorización, definir
umbrales y alertas, y probar el reproceso de mensajes y eventos pendientes.
El chequeo local con umbrales explícitos es:

```powershell
.\scripts\alerts.ps1 -MaxReadyMessages 100 -MaxUnackedMessages 100 -MaxOutboxPending 100
```

En Linux/macOS usar `MAX_READY_MESSAGES=100 MAX_OUTBOX_PENDING=100 bash
scripts/alerts.sh`. El comando devuelve código 2 cuando RabbitMQ, Redis u
Outbox superan el umbral para que CI/monitorización pueda generar una alerta.

## Dependencias

Los seis `requirements.txt` fijan versiones directas reproducibles. La imagen
base y los servicios de infraestructura siguen identificados por etiquetas de
Compose; para producción conviene fijar también sus digests y construir en CI.

## Administración de usuarios y roles

Un administrador puede consultar y modificar usuarios mediante:

- `GET /api/users` (paginado, máximo 100).
- `GET /api/users/{id}`.
- `PATCH /api/users/{id}` con `role` (`Customer`, `seller`, `admin`) o `is_active`.

El endpoint exige rol `admin` y no permite que un administrador se quite su
propio rol o se desactive. La consola visual de `#admin` consume estos contratos
y permite buscar usuarios, cambiar rol/estado y restaurar cambios; la auditoría
de cambios y la gestión visual de productos/categorías siguen fuera de alcance.

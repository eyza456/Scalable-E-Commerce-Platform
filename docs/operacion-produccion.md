# Operación y recuperación

Este documento cubre la preparación local antes de exponer la plataforma. No
sustituye un plan de continuidad probado en infraestructura productiva.

## Persistencia

Compose conserva Redis en `redis_data` con AOF (`everysec`) y el estado durable
de RabbitMQ (Mnesia, colas y metadatos) en `rabbitmq_data`; el cookie Erlang se
mantiene como secreto de runtime de la imagen. PostgreSQL ya usa volúmenes separados por servicio. No usar
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
propio rol o se desactive. Falta todavía una pantalla GUI; la operación queda
disponible por API para el procedimiento administrativo.

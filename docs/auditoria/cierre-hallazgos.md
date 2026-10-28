# Cierre de hallazgos fuera de cobertura

Fecha: 28 de octubre de 2026. Alcance: corregir los hallazgos antes de continuar la auditoria del PDF. La matriz anterior se conserva como evidencia historica del baseline `47c5085`.

| Hallazgo | Correccion | Evidencia reproducible |
| --- | --- | --- |
| Pedido con datos obsoletos | Consulta actual de cada producto al confirmar: existencia, actividad, stock y precio; total calculado con Decimal. Cambio de precio exige confirmacion explicita. | `tests/checkout_stability.py`, `tests/smoke_audit_fixes.py` |
| Actualizaciones de carrito perdidas | Redis WATCH/MULTI/EXEC con reintento y version por mutacion. | `tests/cart_stability.py`; 20 altas HTTP simultaneas conservan cantidad 20 |
| Pedidos duplicados y fallos entre servicios | Checkout durable en PostgreSQL, bloqueo por usuario, identificador unico por version del carrito y worker de recuperacion. Preparacion/finalizacion idempotentes del carrito. | `tests/checkout_stability.py`; cuatro POST simultaneos producen un pedido |
| 500 con entradas validas o demasiado largas | Correo hasta 254 caracteres en esquema y SQL. Contrasena hasta 72 bytes UTF-8 validada antes de bcrypt, sin truncamiento. | `tests/input_limits.py`; correo de 160 caracteres: 201; contrasenas de 80/74 bytes: 422 |
| Fecha final del pago ausente | `processed_at` UTC al pasar a PAID, REJECTED o CANCELLED; permanece NULL mientras esta pendiente. | `tests/payment_stability.py`, pruebas HTTP de aprobacion/rechazo |
| Falta de seguimiento Git | Baseline real `47c5085`, rama `codex/fix-audit-findings` y commit separado de correcciones. Exclusiones de secretos, archivos temporales y respaldos. | `git log --oneline`; `.gitignore`, `.gitattributes`, `.env.example` |

## Contrato de checkout

1. Consultar `GET /api/cart`: devuelve `version` UUID. Enviar esa version en `Idempotency-Key` al hacer `POST /api/orders`. La cabecera es opcional para clientes existentes; usarla permite repetir un intento incluso despues de editar otro carrito.
2. Un pedido nuevo devuelve 201; repetir el mismo checkout devuelve 200 y el mismo pedido. La respuesta incluye `checkout_id`. Con el carrito vacio tras completar la compra, una repeticion sin cabecera tambien recupera el pedido anterior.
3. Si no se puede confirmar el catalogo o coordinar el carrito, el intento persistido devuelve 202 con `checkout_id` y `checkout_status: PENDING`. Consultar `GET /api/orders/checkouts/{checkout_id}`. Solo su propietario puede consultarlo. El worker reintenta cada cinco segundos sin guardar el JWT del usuario.
4. El carrito preparado bloquea ediciones con 409 `CHECKOUT_IN_PROGRESS`. Al terminar se vacia una sola vez. Una confirmacion tardia nunca borra el contenido de una version nueva. Ante rechazo, el carrito se libera conservando sus articulos.
5. Catalogo incompatible devuelve 409: `PRICE_CHANGED`, `INSUFFICIENT_STOCK` o `PRODUCT_UNAVAILABLE`. Para aceptar un precio nuevo, actualizar el articulo mediante PUT del carrito y confirmar la nueva version. Una clave antigua conserva su resultado anterior.
6. Las rutas privadas `/cart/internal/...` requieren clave de servicio y estan bloqueadas en el gateway.

Se revalida la disponibilidad al crear el pedido; la reserva efectiva sigue realizandose al pagar. Un pedido pendiente no aparta unidades. El pago vuelve a comprobar/reservar stock atomicamente antes de confirmar, evitando sobreventa entre pedidos distintos.

## Migraciones y entorno

Aplicadas a las bases locales existentes, sin borrar volumenes:

- `services/user-service/migrations/002_email_length.sql` en user_db.
- `services/order-service/migrations/001_checkouts.sql` en order_db.
- `services/payment-service/migrations/006_processed_at.sql` en payment_db.

Para otra instalacion existente: detener los servicios afectados, ejecutar cada SQL con un cliente PostgreSQL en su base correspondiente y levantar servicios. Las tablas nuevas creadas desde los modelos ya incluyen estos cambios. Cart necesita `INTERNAL_SERVICE_KEY`, agregada al Compose; reconstruir/recrear cart-service y api-gateway para cargar la dependencia y el bloqueo de rutas. Mantener la misma clave interna en los servicios.

Los pagos historicos conservan `processed_at = NULL`: no se inventa una fecha final a partir de `created_at`. Los correos siguen sujetos a validacion de formato y unicidad sin distinguir mayusculas. El limite de contrasena se mide en bytes UTF-8, por ejemplo 72 caracteres ASCII o 36 caracteres «é».

## Verificacion

Ejecutar desde la raiz con Docker Compose activo:

```powershell
powershell -ExecutionPolicy Bypass -File tests/run_stability.ps1
```

La suite incorpora 118 pruebas unittest, escenarios HTTP por gateway y servicios, migracion del catalogo, TTL/DLQ reales y resiliencia del gateway. Las nuevas pruebas cubren fallos antes del commit del pedido, respuesta perdida, finalizacion/aborto del carrito no disponibles y recuperacion del catalogo. Las pruebas utilizan datos propios y limpian los escenarios completados.

Resultado observado: **codigo 0, 118 pruebas aprobadas, 0 fallos**, mas todos los escenarios adicionales. [Resumen verificable](resultado-suite-cierre.json).

Resultados HTTP: [cierre-hallazgos-resultados.json](cierre-hallazgos-resultados.json). El log local de la ejecucion completa es `suite-cierre-hallazgos.log`. `tests/audit_probes.py` ejecuta ahora la regresion vigente; las reproducciones antiguas y `sondas-2026-10-28.json` permanecen en el historial del baseline.

No se reevalua en este cierre la matriz completa del PDF ni se agregan funcionalidades ajenas a estos hallazgos.

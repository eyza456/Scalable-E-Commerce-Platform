# Estabilizacion del backend

Actualizacion: se implementaron [reservas de inventario y recuperacion de pagos](reservas-inventario.md). Esa documentacion describe el flujo vigente de confirmacion y los estados HTTP 201, 202 y 409.

Ver tambien el [cierre de hallazgos de auditoria](auditoria/cierre-hallazgos.md).

## Cambios

- `/users/me` devuelve el perfil autenticado; la prueba administrativa conserva su ruta y permisos propios.
- El descuento manual de stock requiere rol `admin` o `seller`. Una actualizacion SQL condicional evita descuentos concurrentes que dejen stock negativo.
- Se corrigio la coma ausente en el modelo Outbox que impedia arrancar Payment Service.
- La confirmacion PAID y tres entregas Outbox se guardan en una transaccion, despues de reservar stock. Un bloqueo transaccional PostgreSQL por orden serializa solicitudes simultaneas y evita registrar otro pago confirmado para la misma orden.
- Un worker publica entregas pendientes cada cinco segundos. Cada destino conserva su propio estado, intentos y ultimo error. Un destino fallido se reintenta sin reenviar los ya confirmados.
- Con confirmaciones habilitadas, Pika BlockingChannel devuelve `None` al recibir ACK y lanza excepciones ante NACK o un mensaje no enrutable. Las publicaciones respetan ese contrato.
- Product valida el pago confirmado y la pertenencia y contenido de la orden. Admite que la orden siga PENDING mientras Order procesa el mismo evento; conserva la idempotencia de inventario y rechaza ordenes canceladas.
- Order y Product crean sus colas de reintento con espera de cinco segundos y una DLQ. Tras tres intentos, el mensaje queda en DLQ. Solo confirman el mensaje original despues de confirmar su reenvio. No necesitan una politica externa de RabbitMQ para esta recuperacion.

## Instalaciones existentes

La migracion `services/payment-service/migrations/003_reconcile_outbox_destination.sql` se aplico al entorno local. Agrega el destino faltante y conserva los eventos antiguos. Las bases nuevas creadas desde el modelo ya incluyen esa columna.

Para actualizar otra instalacion antigua, detener Payment Service, ejecutar primero la migracion 001 si no existe la tabla y despues la 003 con un cliente PostgreSQL conectado a `payment_db`. La 003 reemplaza la necesidad de ejecutar la antigua 002; tambien admite instalaciones donde 002 ya fue aplicada. Luego iniciar el servicio. No ejecutar un borrado de volumen para migrar.

## Verificacion

Desde la raiz del proyecto, con Docker Compose activo:

```powershell
powershell -ExecutionPolicy Bypass -File tests/run_stability.ps1
```

Las 124 pruebas de regresion verifican perfil, autorizacion, atomicidad de confirmacion/Outbox, reservas y recuperacion, solicitudes y eventos concurrentes, rollback del inventario, confirmaciones Pika y conservacion del original ante fallos de reenvio. Las pruebas PostgreSQL usan esquemas `test_stability_<uuid>` separados y los eliminan al terminar.

Adicionalmente, dos verificaciones con RabbitMQ comprueban reintentos TTL y DLQ en colas exclusivas que se eliminan al finalizar. La prueba HTTP comprueba salud de los seis servicios, perfil y permisos, carrito, pedido, pago, descuento de inventario y las tres entregas Outbox. Crea registros propios y los limpia; conserva una compra con eventos pendientes si falla para permitir su diagnostico.

## Limites que permanecen

- La entrega es al menos una vez: un cierre entre la confirmacion del broker y el commit puede repetir un mensaje. Order y Product toleran duplicados; las notificaciones actuales son impresiones en consola y pueden repetirse.
- Los pagos nuevos requieren una reserva confirmada antes de PAID. Los pagos historicos anteriores a esta mejora mantienen el flujo antiguo y no se reconstruyen automaticamente. Una futura pasarela real necesitara su propio mecanismo de cobro y reembolso.
- Los eventos que agotan los tres intentos requieren recuperacion operativa. Se conserva el script de recuperacion de Product. Un mensaje antiguo ya presente en su DLQ no fue reprocesado automaticamente.
- No se reconstruyen eventos de pagos historicos que se guardaron sin Outbox.
- El carrito y la creacion de pedidos todavia requieren revalidacion final de precios/disponibilidad y control de concurrencia para completar el MVP.

Se implementaron [categorias, busqueda y filtros](catalogo.md), [actualizacion de perfil](perfil-usuario.md), [historial y cancelaciones](pedidos.md) y [API Gateway](api-gateway.md). Los pagos ya se rechazan cuando falta stock; simular otros motivos de rechazo y completar la validacion final del MVP siguen pendientes.

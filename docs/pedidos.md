# Historial y cancelacion de pedidos

## Historial privado

```http
GET /orders?status=PENDING&skip=0&limit=20
Authorization: Bearer <token>
```

Devuelve una lista con los pedidos del usuario autenticado, sus productos y totales originales. No permite elegir otra cuenta. Se ordena por fecha descendente y, si coinciden, por ID descendente.

- `skip`: entero mayor o igual a cero.
- `limit`: entre 1 y 100; por defecto 20.
- `status`: opcional, uno de `PENDING`, `CANCELLING`, `CANCELLED`, `PAID`, `PROCESSING`, `SHIPPED`, `DELIVERED`.
- Sin coincidencias: lista vacia. Parametros invalidos: HTTP 422. Sin autenticacion: HTTP 401.

## Cancelacion

```http
POST /orders/123/cancel
Authorization: Bearer <token>
```

Solo se cancelan pedidos pendientes del propio usuario. Una cuenta ajena recibe 404. La solicitud no necesita cuerpo ni permite seleccionar otro usuario.

| Respuesta | Estado y significado |
| --- | --- |
| 200 | `CANCELLED`: pagos bloqueados e inventario liberado; o el pedido ya estaba cancelado. |
| 202 | `CANCELLING`: solicitud durable, pendiente de completar entre servicios. Se recupera automaticamente. |
| 409 | Ya se confirmo el pago o el pedido avanzo de estado; requiere un flujo de reembolso. |

Se puede consultar el detalle o historial para observar el resultado de una cancelacion pendiente. Repetir la solicitud no devuelve stock dos veces.

## Coordinacion entre servicios

1. Order guarda `CANCELLING` antes de llamar a otros servicios.
2. Payment serializa cancelacion, creacion y confirmacion del pago con el mismo bloqueo PostgreSQL por pedido. Si un pago `PAID` gano la carrera, rechaza la cancelacion. Order conserva/restaura el estado pagado, aunque el evento de pago todavia no haya llegado.
3. Si la cancelacion gana, Payment guarda una barrera durable en `order_cancellations` y cambia los intentos `PENDING` a `CANCELLED`. Impide crear o recuperar pagos nuevos del pedido.
4. Product usa el mismo bloqueo por pedido para reservar y liberar. Devuelve las unidades de una reserva `RESERVED`, marca `RELEASED` y guarda una barrera en `inventory_cancellations`. Incluso si no habia reserva, la barrera impide que una solicitud tardia descuente inventario despues de cancelar.
5. Payment marca la liberacion como `DONE`; solamente entonces Order confirma `CANCELLED`.

Los recuperadores de Order y Payment reintentan cada cinco segundos las etapas incompletas. Una caida, timeout o respuesta perdida conserva los estados intermedios; no se informa cancelacion completada antes de liberar inventario.

Las reservas `CONSUMED` no se liberan con este flujo: pertenecen a pagos confirmados. Product admite procesar un pago ya verificado mientras Order esta transitoriamente `CANCELLING`, porque ese pago impide finalizar la cancelacion. El consumidor de Order espera la decision de Payment.

Los endpoints internos de cancelacion y liberacion requieren la clave interna y verifican la etapa anterior en el servicio autoritativo. No se aceptan cantidades de reposicion enviadas por clientes. Los productos con reservas `RESERVED` no pueden eliminarse por la API, para permitir su devolucion posterior.

## Migraciones y limites

Se aplicaron al entorno local sin borrar datos:

- Payment: `migrations/005_order_cancellations.sql`.
- Product: revision Alembic `b1c5a09e3d72`.

Para otra instalacion, aplicar ambas con las imagenes actualizadas antes de habilitar cancelaciones. Order almacena estados en texto, por lo que `CANCELLING` no requiere cambiar su tabla. Payment registra el modelo de cancelaciones en la creacion de esquemas nuevos; Product requiere `alembic upgrade head`.

Este flujo no implementa reembolsos, cancelacion de pedidos pagados/enviados ni revierte pagos historicos. Conflictos de datos ajenos al flujo normal permanecen pendientes para revision en lugar de inventar stock o confirmar una cancelacion incierta.

## Pruebas

Se agregaron 22 pruebas: 11 de historial/cancelacion en Order, cinco de coordinacion en Payment y seis de liberacion en Product. Incluyen aislamiento entre usuarios, paginacion estable, recuperacion ante caidas, cancelacion frente a confirmacion de pago, reservas tardias y liberaciones concurrentes.

La prueba `tests/smoke_orders.py` ejecuta entre servicios una reserva pendiente real y su cancelacion publica. Verifica la reposicion una sola vez, la proteccion de pedidos pagados y la privacidad del historial. Limpia los registros creados al terminar correctamente; conserva compras incompletas para diagnostico.

Todo esta incluido en `tests/run_stability.ps1`.

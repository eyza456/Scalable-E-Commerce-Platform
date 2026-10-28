# Reserva de inventario y recuperacion de pagos

Actualizacion: los pedidos pendientes ahora permiten [cancelacion coordinada y liberacion de reservas](pedidos.md). Las reservas no se liberan ante un simple timeout; se liberan tras bloquear de forma durable los pagos del pedido.

## Comportamiento

1. Payment consulta la orden autenticada y guarda un intento `PENDING`, su transaccion y una copia inmutable de los datos necesarios para el evento. Todavia no confirma el pago.
2. Payment solicita la reserva por transaccion a Product usando la clave interna. Product obtiene las cantidades desde ese intento persistido; no acepta cantidades proporcionadas por un cliente externo.
3. Product descuenta las unidades disponibles y registra la reserva en una sola transaccion. Agrupa productos repetidos, actualiza en orden de ID y exige stock suficiente y producto activo. Si falla un producto, revierte todos los descuentos.
4. Tras confirmar la reserva, Payment guarda `PAID` y sus tres entregas Outbox en una transaccion. Product procesa el evento convirtiendo la reserva a `CONSUMED`, sin volver a descontar. Los eventos duplicados siguen siendo idempotentes.

`stock` representa unidades disponibles, por lo que disminuye al reservar. La reserva conserva las unidades comprometidas mientras los consumidores terminan de actualizar pedido e inventario.

## Caidas y falta de stock

- Si no hay unidades suficientes, Payment guarda `REJECTED`, no publica `PAYMENT_COMPLETED` y devuelve HTTP 409 con `code=INSUFFICIENT_STOCK` y `transaction_id`. La orden continua pendiente y puede reintentarse con una nueva transaccion si se repone stock.
- Si Product no responde o la respuesta es ambigua, Payment conserva `PENDING` y devuelve HTTP 202 con el intento. El cliente puede consultar `GET /payments/transactions/{transaction_id}`. HTTP 202 no significa pago confirmado.
- Un recuperador revisa intentos pendientes cada cinco segundos. Retoma la misma transaccion y reserva. Si el proceso cae despues de reservar o se pierde la respuesta HTTP, no descuenta de nuevo.
- Si falla el commit de `PAID`/Outbox, el intento durable sigue pendiente y el recuperador lo completa. Si el commit ya ocurrio pero se perdio su respuesta, el estado `PAID` y Outbox permanecen juntos.
- HTTP y el recuperador bloquean el intento para evitar confirmaciones duplicadas. La creacion de intentos para una misma orden se serializa con un bloqueo PostgreSQL independiente.
- No se liberan reservas ante un simple timeout: hacerlo podria vender unidades de un pago cuya confirmacion ya se guardo. Se recuperan hacia la confirmacion usando el intento durable. Este flujo procesa pagos simulados; una pasarela real requerira su propio protocolo de cobro y reembolso.

## Despliegue y compatibilidad

Se aplicaron al entorno local, sin borrar volumenes:

- Payment: `services/payment-service/migrations/004_payment_intent.sql`, que agrega el snapshot JSON nullable.
- Product: revision Alembic `86e4d1207a31`, que crea `inventory_reservations`.

Para otra instalacion existente, pausar temporalmente nuevos pagos, aplicar la migracion SQL sobre `payment_db` y ejecutar `alembic upgrade head` dentro de Product con la imagen actualizada. Iniciar Payment despues de las migraciones. En una instalacion nueva, migrar Product antes de admitir pagos; Payment crea su esquema desde los modelos al iniciar.

Los pagos historicos sin snapshot no se convierten automaticamente en intentos recuperables. Los eventos historicos sin identificador de reserva conservan el procesamiento anterior. Un evento de un pago nuevo no puede omitir su reserva para forzar otro descuento: se compara con el pago consultado en Payment.

Las reservas no caducan automaticamente mientras existe un intento pendiente: el recuperador las reutiliza. Conflictos de datos o intentos historicos incompatibles requieren revision, en lugar de confirmar o rechazar un cobro basandose en una respuesta incierta.

## Pruebas

```powershell
powershell -ExecutionPolicy Bypass -File tests/run_stability.ps1
```

La suite incluye 124 pruebas de regresion, incluidas las nuevas comprobaciones de checkout, concurrencia del carrito, limites de entrada y fecha final del pago. Tambien verifica la migracion del catalogo con datos antiguos. Usa esquemas PostgreSQL desechables.

Ademas comprueba TTL y DLQ reales, una compra HTTP completa y dos escenarios de inventario entre servicios:

- Dos ordenes solicitan dos unidades cada una de un producto con tres disponibles: solo un pago se confirma, el otro se rechaza y queda una unidad.
- Se guarda un intento y su reserva, y el proceso termina antes de confirmar el pago: el recuperador completa pago y eventos usando la misma reserva y el stock no vuelve a disminuir.

Las pruebas HTTP limpian los registros que crean cuando terminan correctamente. Conservan los registros de una compra incompleta para diagnostico.

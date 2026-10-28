# Cierre de pendientes: pedidos y rechazos simulados

## Estado

- Precios y disponibilidad: el checkout consulta el catalogo actual, comprueba actividad y stock, recalcula el total con Decimal y rechaza cambios de precio con 409 hasta que el cliente actualice el carrito.
- Compras simultaneas desde un carrito: version UUID, operaciones atomicas Redis, checkout persistido, bloqueos PostgreSQL y recuperacion idempotente. Varias confirmaciones del mismo carrito devuelven el mismo pedido.
- Rechazos adicionales: simulacion determinista de fondos insuficientes, tarjeta vencida y rechazo del emisor. El cliente puede elegir el resultado de cada intento; sin parametro se conserva el resultado aprobado habitual.

## Probar un rechazo

Enviar al gateway con el token del propietario de un pedido PENDING:

```http
POST /api/payments
Authorization: Bearer <token>
Content-Type: application/json

{
  "order_id": 123,
  "method": "card",
  "simulation_result": "insufficient_funds"
}
```

| simulation_result | Resultado | HTTP |
| --- | --- | --- |
| approved (predeterminado) | PAID, sujeto a reserva de stock | 201; 202 si inventario temporalmente no disponible |
| insufficient_funds | REJECTED / INSUFFICIENT_FUNDS | 409 |
| expired_card | REJECTED / EXPIRED_CARD | 409 |
| card_declined | REJECTED / CARD_DECLINED | 409 |
| Valor desconocido | Error de validacion sin crear intento | 422 |

El 409 incluye `detail.code`, `detail.message` y `detail.transaction_id`. Consultar `GET /api/payments/transactions/{transaction_id}` devuelve `status`, `rejection_code` y `processed_at`. El motivo tambien esta disponible en la consulta interna protegida. Un rechazo real por stock conserva `INSUFFICIENT_STOCK`.

Los rechazos simulados se deciden antes de reservar inventario: no descuentan unidades ni crean eventos PAYMENT_COMPLETED. El pedido sigue PENDING y puede recibir otro intento, por ejemplo approved. Cada nuevo intento rechazado tiene su propia transaccion; la proteccion contra doble pago aprobado permanece activa.

El resultado del intento se guarda antes de procesarlo. Si el proceso se interrumpe, el worker recupera esa misma decision. Una solicitud no puede cambiar el resultado de un intento PENDING. La cancelacion de la orden tiene prioridad sobre la simulacion. La fecha final de una transaccion terminal no cambia con la recuperacion repetida.

Este servicio simula autorizaciones; no recibe datos bancarios ni llama a una pasarela de cobro real. No se utiliza aleatoriedad para permitir pruebas reproducibles. El stock se revalida al crear pedidos y se reserva efectivamente al pagar.

## Instalacion existente

Aplicada localmente `services/payment-service/migrations/007_simulated_rejections.sql`, sin eliminar datos. En otra instalacion: detener Payment Service, aplicar ese SQL en payment_db con un cliente PostgreSQL y reiniciar el servicio. La migracion agrega `simulation_result` y `rejection_code`; los rechazos historicos de este sistema, que solo se producian por falta de stock, reciben INSUFFICIENT_STOCK. Las bases nuevas creadas desde el modelo incluyen ambos campos.

## Evidencia

Resultado observado: **124 pruebas aprobadas, 0 fallos, codigo de salida 0**. Tambien pasaron los escenarios HTTP, RabbitMQ y resiliencia del gateway.

- `tests/payment_stability.py`: 29 pruebas, incluidas persistencia de los tres motivos, ausencia de reservas/eventos, recuperacion tras interrupcion, rechazo de cambios del intento pendiente, cancelacion prioritaria y posterior pago aprobado.
- `tests/checkout_stability.py` y `tests/cart_stability.py`: 22 pruebas de revalidacion, concurrencia y recuperacion del checkout/carrito.
- `tests/smoke_audit_fixes.py`: catalogo obsoleto y cuatro confirmaciones HTTP simultaneas con un unico pedido.
- `tests/smoke_payment_rejections.py`: tres rechazos HTTP reales por gateway, consultas de transaccion, comprobacion SQL de cero eventos/reservas y reintento aprobado con un solo descuento.
- [Resultados HTTP de rechazos](auditoria/rechazos-pago-resultados.json).

Ejecutar toda la suite con `powershell -ExecutionPolicy Bypass -File tests/run_stability.ps1`. Resultado de esta etapa en [resumen de ejecucion](auditoria/resultado-suite-pendientes.json); log local `docs/auditoria/suite-pendientes.log`. La auditoria original y el cierre previo se conservan como evidencias historicas.

# Pago simulado conectado

Revision local del 29 de octubre de 2026. Interfaz en `frontend/app/payments.js`,
visible debajo del pedido confirmado. Conserva la direccion visual de Stitch.

## Funciones y recuperacion

- Simular aprobacion, fondos insuficientes, tarjeta vencida y rechazo del emisor.
- Mostrar referencia, importe, motivo y fecha final del intento persistido.
- Consultar el intento pendiente sin volver a enviar el pago.
- Recuperar respuestas perdidas mediante el ultimo intento del pedido.
- Permitir otro intento solo despues de consultar el estado; no hay POST automaticos.
- Recuperar tras recarga/login desde el ultimo checkout del carrito.
- Cerrar sesion borra referencias y resultados privados de la interfaz.

Nuevo endpoint de lectura: `GET /payments/orders/{order_id}/latest`, publicado
por el gateway en `/api/payments/orders/{order_id}/latest`. Filtra por propietario
en SQL, ordena por ID de intento descendente y utiliza `PaymentResponse` para no
exponer el snapshot interno de eventos. Devuelve 404 tanto si no hay intentos
propios como si corresponden a otra cuenta. Requiere JWT y no modifica pagos,
stock ni eventos. No requiere migracion.

La interfaz verifica el estado del pedido y el ultimo intento antes de enviar.
Un PAID/PENDING existente impide otra simulacion. Un rechazo permite un nuevo
intento solicitado expresamente. Un resultado desconocido bloquea cambiar la
simulacion. Si se ofrece reenvio manual, conserva el resultado elegido. Se mantiene
la serializacion del backend por pedido: no se añade una clave idempotente por
intento de pago. Los reenvios manuales de rechazos pueden registrar otro rechazo;
no se afirma deduplicacion de todos los intentos historicos. No hay doble PAID.

El estado del pago se muestra independientemente del pedido. Tras aprobar,
se consulta el pedido para reflejar su transicion por eventos; no se marca PAID
en el navegador sin leer su estado real. El sondeo automatico usa solo GET, es
acotado y se detiene al salir de la pantalla o cerrar sesion.

## Verificacion

- **39 pruebas existentes** de pago aprobadas, incluyendo reservas, recuperacion,
  Outbox y concurrencia, ejecutadas dentro de payment-service.
- **3 pruebas adicionales** (`tests/payment_latest.py`) en esquema PostgreSQL
  desechable: ultimo intento, privacidad 404 y lectura de PENDING sin mutacion.
- **11 escenarios de navegador** (`tests/frontend_payments.cjs`): creacion del
  pedido sin pago automatico; tres rechazos sin stock/eventos; aprobacion posterior;
  autenticacion/propiedad; respuesta perdida; 202; perdida antes del servidor;
  dos pestañas; stock agotado; fallo en consulta previa; recarga, movil y logout.
- Regresion de **12 escenarios** de carrito/checkout y **13** de acceso/catalogo.

Resultado y hashes: [pagos.json](pagos.json) y [pruebas Python observadas](pagos-backend.json).
Los errores de transporte, el 202
y el fallo de consulta previa se inyectan en Playwright y estan identificados.
Los pagos, reservas, eventos y descuentos finales se verifican en servicios reales.
Dos pestañas generan un solo PAID y tres eventos de destino para ese pago.
Las fixtures se eliminan despues de publicar sus eventos y consumir reservas.
Las capturas de [rechazo](pago-rechazado.png) y [aprobacion movil](pago-aprobado-mobile.png)
muestran fixtures temporales ya eliminadas. No son contenido actual del catalogo.

No se volvio a ejecutar la suite completa historica de 153 pruebas ni el benchmark
RNF-01. Las 3 pruebas nuevas son adicionales, no se suman a un resultado historico
como si se hubiera repetido esa suite.

## Limites y siguiente paso

No es una pasarela bancaria y no se cobra dinero. La aprobacion SI modifica el
inventario local y genera eventos reales de prueba. No introducir datos bancarios.
La sesion sigue solo en memoria. El carrito conserva unicamente su ultimo checkout;
para consultar pedidos anteriores ahora se utiliza el [historial integrado](pedidos.md).
Continua pendiente la edicion visual del perfil.

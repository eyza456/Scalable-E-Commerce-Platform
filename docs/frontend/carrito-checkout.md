# Carrito y checkout conectados

Revision local del 29 de octubre de 2026. Amplia la interfaz basada en Stitch
sin modificar los microservicios ni las rutas del API Gateway. Disponible en
`http://127.0.0.1:8080/` mediante `compose.frontend.yml`.

## Recorrido

Iniciar sesion -> abrir detalle de producto -> elegir cantidad -> agregar ->
abrir carrito -> actualizar/quitar productos -> revisar pedido -> confirmar.
La pantalla final presenta el numero, estado, items y total reales del pedido.
No se procesa pago en esta etapa; el pedido queda pendiente de pago.

El carrito se consulta mediante `/api/cart`. Sus mutaciones se envian a
`/api/cart/items` y `/api/cart/items/{product_id}`. El servidor decide el precio,
la disponibilidad y las cantidades permitidas; el navegador no calcula el importe
que se almacena en el pedido. Se permite actualizar una cantidad para refrescar
el precio antes de volver a revisar un checkout rechazado.

## Recuperacion e integridad

- Confirmar envia la version del carrito en `Idempotency-Key`, no una clave nueva.
- No hay POST automaticos de reintento. Si se pierde una respuesta, se consulta
  el carrito y el resultado del checkout. Si no existe y el carrito conserva su
  version, se ofrece reintento manual con la misma referencia.
- Los resultados pendientes se consultan solo con GET y sondeo acotado. Cambiar
  de pantalla o de sesion interrumpe el sondeo; las respuestas de una sesion
  anterior no deben rellenar el contenido privado de otra.
- El carrito congelado y las mutaciones inciertas bloquean nuevas modificaciones
  hasta consultar su estado. Los errores se distinguen del carrito vacio.
- Cambios de precio, falta de stock o version modificada exigen revisar el carrito.
- Al recargar e iniciar sesion de nuevo, el carrito permite encontrar un checkout
  activo o el ultimo pedido de su version consumida. No se persisten tokens ni
  referencias en localStorage, sessionStorage o cookies.
- El carrito no reserva stock. La reserva pertenece al procesamiento del pago,
  que continua pendiente de integracion visual.

## Verificacion

`tests/frontend_commerce.cjs` ejecuta **12 escenarios** de navegador usando el
frontend, gateway, Redis, PostgreSQL y servicios locales reales. Resultado en
[carrito-checkout.json](carrito-checkout.json), con hashes de archivos y limpieza.

Incluye login requerido, altas/actualizacion/eliminacion y totales, cambios de
precio y stock, cambios desde otro cliente, recuperacion despues de recarga,
respuesta perdida despues de crear un pedido y perdida antes de alcanzar el
servidor. Tambien verifica sondeo de 202 y dos pestañas confirmando la misma
version: ambas obtienen el mismo pedido y se verifica un unico registro adicional
en PostgreSQL. El checkout movil y el carrito caben en 390 px; cerrar sesion
elimina el contenido privado. No hubo errores de JavaScript en esos recorridos.

Las respuestas perdidas y el 202 se inyectan desde Playwright y se identifican
como tales en el informe: no se afirma una caida real de los servicios. El 202
inyectado sigue a la creacion de un pedido real y su consulta final tambien es
real. Las pruebas crean solo sus propias cuentas/productos/carritos/pedidos y los
eliminan al terminar; no procesan pagos ni dejan reservas.

Se repite ademas la regresion de **13 escenarios** de acceso y catalogo descrita
en [integracion.md](integracion.md). No se vuelve a contar la suite historica de
153 pruebas del backend como ejecutada en esta etapa, ni se repite la carga RNF-01.

Capturas con fixtures temporales ya eliminadas:
[carrito escritorio](carrito-desktop.png), [carrito movil](carrito-mobile.png),
[checkout movil](checkout-mobile.png).

## Siguiente etapa

Integrar pago simulado aprobado/rechazado y su recuperacion, despues historial,
cancelacion y edicion de perfil. Los prototipos de esas pantallas siguen en
`frontend/stitch/`; no representan funciones ya conectadas.

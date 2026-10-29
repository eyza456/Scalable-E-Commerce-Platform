# Historial y cancelacion conectados

Revision local del 29 de octubre de 2026. Modulo `frontend/app/orders.js`, basado
en la direccion visual de Stitch y las APIs existentes. No modifica el backend.

## Funciones

- Mis pedidos con diez filas por pagina y filtro por los siete estados del backend.
- Detalle privado con fecha, estado, productos/cantidades y total del servidor.
- Consulta y pago simulado de pedidos anteriores. Reutiliza `payments.js` con
  estado y elementos DOM independientes del checkout activo.
- Cancelacion de PENDING con confirmacion en dialogo. CANCELLING muestra seguimiento;
  PAID y estados posteriores no ofrecen cancelar. El servidor resuelve carreras.
- Consulta con GET despues de respuestas perdidas o conflictos; no hay POST de
  reintento automatico. El sondeo de CANCELLING es acotado y se detiene al navegar
  o salir de sesion. Hay consulta manual y recuperacion de errores de lectura.
- Vacios, carga y errores diferenciados; contenido privado eliminado al salir.

Rutas del navegador: `#pedidos` y `#pedidos/{id}`. Solicitudes a `/api/orders`,
`/api/orders/{id}` y `/api/orders/{id}/cancel`, exclusivamente por el gateway.
No usa endpoints internos, altera estados administrativos ni procesa reembolsos.

## Verificacion observada

**10 escenarios nuevos de navegador** en `tests/frontend_orders.cjs`, con
resultado, hashes y limpieza en [pedidos.json](pedidos.json). Incluyen sesion
requerida, historial vacio, doce pedidos reales para paginacion, filtro, detalle,
desistir del dialogo, cancelacion real, respuesta perdida, 202, pago de pedido
antiguo y proteccion de PAID, privacidad entre cuentas, error recuperable y movil.

La perdida de respuesta y el 202 se inyectan desde Playwright y estan identificados.
Ambos consultan despues el estado de una cancelacion real, sin repetir el POST.
El escenario de pago historico usa reservas y eventos reales del backend.

La regresion repite los **36 escenarios anteriores**: 13 de acceso/catalogo,
12 de carrito/checkout y 11 de pagos. Son 46 escenarios de navegador en total.
No se afirma que se haya repetido la suite completa historica del backend ni RNF-01.

Adicionalmente, `tests/smoke_orders.py` verifica por HTTP una reserva real pendiente,
su liberacion una sola vez tras cancelar y el rechazo de cancelar un pago ya
confirmado. Resultado observado en [pedidos-api.json](pedidos-api.json). Este
escenario controla un bloqueo de confirmacion en una fixture propia para mantener
la reserva pendiente; el navegador usa la misma API publica de cancelacion.

Capturas revisadas: [escritorio](historial-desktop.png), [movil](historial-mobile.png)
y [pedido cancelado](pedido-cancelado-mobile.png). Contienen datos temporales ya
eliminados. Las pruebas no dejan cuentas, pedidos, pagos ni reservas de fixture.

## Siguiente etapa

Editar nombre/correo en Mi cuenta y sustituir el token devuelto por el servidor,
conservar la sesion correcta al cambiar el correo y verificar duplicados/validacion.
No hay gestion administrativa visual de usuarios/productos ni pasarela bancaria real.

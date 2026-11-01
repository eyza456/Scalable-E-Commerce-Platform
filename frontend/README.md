# Frontend Nexo

Propuestas visuales generadas con Google Stitch para el backend existente.
Proyecto Stitch: `3316878412824520653` (Ecommerce Microservices - Frontend MVP).
Nombre Nexo provisional; no representa una marca definitiva.

## Aplicacion conectada

`app/` contiene registro, inicio de sesion, consulta de la cuenta autenticada,
cierre local de sesion, edicion de nombre/correo, catalogo con filtros por nombre/categoria/disponibilidad,
paginacion, detalle, carrito, creacion de pedidos, pago simulado, historial y cancelacion. Los productos,
precios y stock vienen del backend real.
No se crean datos de demostracion al arrancar. La vista de carrito incluye vaciado
completo con confirmacion accesible. Las cuentas con rol `admin` disponen de una
consola visual para listar usuarios y actualizar rol o estado activo; la API sigue
siendo la autoridad y protege la propia cuenta del administrador.

Con el backend configurado y sus migraciones aplicadas, desde la raiz:

```powershell
docker compose -f docker-compose.yml -f compose.frontend.yml up -d --build frontend
```

Abrir `http://127.0.0.1:8080/`. Se puede cambiar `FRONTEND_PORT` en el entorno.
Si el backend ya esta activo, agregar `--no-deps` para reconstruir solo frontend.
El contenedor sirve HTML/CSS/JS propios, sin dependencias JavaScript ni Tailwind
CDN. Google Fonts es opcional, con alternativas del sistema. Las imagenes usan
`image_url` del producto; si faltan o no son HTTP(S), se muestra un marcador.
Los textos de productos se insertan como texto, nunca como HTML.

El navegador llama a `/api/...` en el mismo origen. El Nginx del frontend reenvia
al API Gateway, sin acceder directamente a los microservicios ni habilitar CORS
global. El gateway conserva sus rutas y bloqueo de endpoints internos.

El token vive solo en memoria, sin localStorage, sessionStorage ni cookies. Se
verifica con `/api/users/me` al iniciar sesion. Recargar/cerrar la pagina termina
la sesion local. Cerrar sesion borra el token en esta pagina; no revoca tokens ya
emitidos en otros clientes. Registrar una cuenta no inicia sesion automaticamente.
Las cuentas registradas persisten en el backend. No hay reintentos automaticos.

Escucha en loopback HTTP para desarrollo local. HTTPS, sesiones persistentes y
despliegue publico requieren una etapa posterior.

## Prototipos de Stitch

Siete pantallas exportadas: catalogo, acceso/registro, detalle, carrito, checkout,
pedidos y perfil. Recursos de origen registrados en `stitch-manifest.json`.
Las copias locales corrigen textos generados; no modifican los originales de Stitch.

Para abrir la galeria, ejecutar desde la raiz del repositorio:

```powershell
python -m http.server 5173 --bind 127.0.0.1 --directory frontend
```

Abrir `http://127.0.0.1:5173/`. La galeria permite alternar pantallas y ancho movil.

La galeria `index.html` y `stitch/` contienen prototipos con datos de ejemplo. No hay autenticacion ni
compras reales conectadas al backend. El contador del carrito del catalogo es
una simulacion local. No introducir credenciales ni datos bancarios reales.

El servidor de galeria en 5173 no reenvia APIs. La aplicacion conectada se abre
en 8080. El Dockerfile copia exclusivamente `app/`, sin publicar los prototipos.

La vista previa de Stitch usa recursos externos de Google Fonts, imagenes y Tailwind CDN;
necesita Internet. La implementacion final debera compilar sus estilos y gestionar
sus dependencias, accesibilidad y recursos de forma explicita.

## Recorrido del cliente

1. Registro e inicio de sesion: integrados en `app/`.
2. Catalogo, categorias y detalle: integrados en `app/`.
3. Carrito integrado: altas desde detalle, actualizar cantidad/precio y quitar.
4. Checkout integrado: revision y confirmacion por `/api/orders`, recuperacion
   mediante `/api/orders/checkouts/{id}` y visualizacion del pedido creado.
5. Pago simulado integrado: `/api/payments`; aprobado o rechazado, con consulta
   del ultimo intento antes de permitir otro envio.
6. Historial y cancelacion integrados segun estado: `/api/orders`.
7. Consulta y edicion del perfil integradas, con sustitucion del token al guardar.
8. Consola administrativa de usuarios/roles y vaciado completo del carrito con dialogos accesibles.

Todas las llamadas del frontend final se dirigiran al API Gateway. Al integrar,
consultar los contratos actuales y OpenAPI: los identificadores, precios, stock,
estados y permisos del servidor prevalecen sobre los datos de ejemplo del diseño.
Un checkout puede responder pendiente; se debe recuperar su resultado sin crear
otro pedido. Nunca reintentar automaticamente una mutacion de resultado incierto.

## Orden de trabajo

Diseno de pantallas y revision visual -> navegacion adaptable -> integracion con
API Gateway -> pruebas de recorrido completo y accesibilidad.

Los prototipos no acreditan cumplimiento funcional de requisitos nuevos ni alteran
la matriz auditada del backend. No se incluyen envios, promociones, reseñas,
recuperacion de contraseña ni pagos bancarios reales.

Las credenciales de Stitch se configuran en Codex fuera del repositorio y nunca
deben incluirse en los archivos que se sirven al navegador.

## Verificacion de la aplicacion

Con los servicios activos, disponer de Playwright y Microsoft Edge en el host.
Si Playwright pertenece a un runtime externo, configurar `NODE_PATH` a su
directorio node_modules. Desde la raiz ejecutar `node tests/frontend_browser.cjs`.
`BROWSER_CHANNEL=chrome` permite Chrome; `FRONTEND_URL` permite otra URL local.

El test crea una categoria, dos productos y una cuenta con identificador unico;
elimina exclusivamente esos registros al finalizar. Usa APIs reales e identifica
expresamente los errores 503/401 inyectados. Genera `docs/frontend/integracion.json`
y capturas. Es adicional a la suite del backend; no cambia el recuento historico
de 153 pruebas. No necesita administradores reales ni registra credenciales.

## Carrito y checkout

`app/commerce.js` controla el carrito y la creacion del pedido. Requiere iniciar
sesion. El alta del producto se hace desde su detalle; las cantidades admiten
1 a 100 unidades, limitadas tambien por el stock que valida el servidor.

La confirmacion envia la version real del carrito como `Idempotency-Key`. Los
botones se bloquean mientras hay una mutacion en curso. Ante una respuesta perdida,
se consulta el carrito y el checkout antes de ofrecer un reintento explicito con
la misma clave. Nunca se repite automaticamente un POST. Los checkouts pendientes
se consultan con GET hasta diez veces mientras se muestra el checkout, luego se
permite consulta manual. Navegar fuera o cerrar sesion detiene el sondeo.

Si otra pestaña modifica el carrito, se exige revisarlo. Si cambia precio, stock
o actividad, el servidor puede rechazar el checkout. Actualizar una cantidad
refresca su precio en el carrito; despues se puede confirmar de nuevo.

Recargar sigue cerrando la sesion en memoria. Al volver a entrar al carrito, se
consulta `checkout_id` o, si esta vacio, `last_checkout_id` para recuperar el pedido
existente. No se guardan tokens ni referencias en almacenamiento del navegador.
Un pedido creado queda pendiente de pago. El carrito no equivale a una reserva
de stock; el pago simulado aprobado reserva/consume inventario real del entorno.

Prueba adicional: `node tests/frontend_commerce.cjs`. Utiliza Playwright/Edge con
las mismas variables del test anterior y fixtures propias eliminadas al terminar.
Resultado y capturas en `docs/frontend/carrito-checkout.json` y
[detalle de verificacion](../docs/frontend/carrito-checkout.md).

## Pago simulado

La pantalla del pedido incorpora aprobacion y rechazos por fondos insuficientes,
tarjeta vencida o emisor. No pide datos bancarios reales. Los rechazos de autorizacion
no reservan stock; la aprobacion usa las reservas/eventos reales de este backend.
El rechazo por falta de stock tambien se muestra con su motivo.

`app/payments.js` consulta el ultimo intento y el estado del pedido antes de cada
envio explicito. No envia POST automaticos. Ante perdida de respuesta, consulta
`GET /api/payments/orders/{order_id}/latest`; este endpoint nuevo filtra por usuario
autenticado y responde 404 para pedidos sin intentos propios. La referencia conocida
se consulta tambien por `/api/payments/transactions/{transaction_id}`.

Los intentos pendientes se consultan con GET, hasta diez sondeos automaticos, con
consulta manual posterior. Cambiar de pantalla o cerrar sesion detiene el sondeo.
La seleccion del resultado queda bloqueada mientras se procesa un intento. Si no
se confirma su registro, puede ofrecerse reintento explicito de la misma simulacion.
El servidor serializa por pedido y evita dos pagos PAID/reservas duplicadas; un
nuevo rechazo explicitamente solicitado puede registrar otro intento rechazado.

Tras actualizar una instalacion existente, recargar tambien payment-service:

```powershell
docker compose up -d --build payment-service
docker compose -f docker-compose.yml -f compose.frontend.yml up -d --build --no-deps frontend
```

No hay migracion nueva. Para verificar: `node tests/frontend_payments.cjs`, mas
las dos pruebas de navegador anteriores. Las pruebas Python adicionales se ejecutan
dentro de payment-service:

```powershell
Get-Content tests/payment_latest.py -Raw | docker compose exec -T payment-service python -
```

Consultar [evidencia y limites](../docs/frontend/pagos.md).

## Historial y cancelacion

`app/orders.js` implementa Mis pedidos (`#pedidos`) y detalle (`#pedidos/{id}`).
Consulta solo pedidos del usuario autenticado, con filtro por estado y paginacion.
Permite consultar/pagar un pedido anterior mediante una instancia independiente
del mismo componente de pago; no sustituye el checkout actual del carrito.

La cancelacion solo se ofrece para PENDING y exige confirmacion en un dialogo.
El servidor decide si procede, coordina la liberacion de reservas y rechaza pagos
confirmados. Un resultado CANCELLING se consulta con GET hasta diez veces; siempre
queda disponible la consulta manual. No hay reenvio automatico del POST de cancelacion.
Si se pierde la respuesta o se produce conflicto, se lee el estado real del pedido.

Prueba: `node tests/frontend_orders.cjs`, con Playwright/Edge y los mismos ajustes
de las pruebas anteriores. `python -X utf8 tests/smoke_orders.py` verifica tambien
la liberacion real de una reserva y proteccion de un pago confirmado en backend.
Consultar [evidencias del historial](../docs/frontend/pedidos.md).
La edicion del perfil y renovacion del token tambien estan integradas.

## Edicion del perfil

En Mi cuenta, Editar perfil permite modificar nombre/correo y descartar borradores.
Solo se envian los campos cambiados a `PUT /api/users/me`. Se comprueban limites
y espacios, y los duplicados/errores del servidor conservan el formulario editable.
No hay campos para modificar roles, permisos, contraseñas o identificadores.

Una respuesta correcta sustituye juntos perfil y token en memoria; los proximos
requests autenticados usan el token devuelto. El correo nuevo se usa en futuros
inicios de sesion. No se guardan tokens en almacenamiento del navegador.

Si se pierde la respuesta o hay un 5xx, el cambio puede haberse aplicado. Se cierra
la sesion local y se pide autenticar de nuevo, sin repetir la actualizacion. El
formulario de acceso sugiere el correo ingresado; si no se aplico, usar el anterior.
Una respuesta tardia no puede restaurar la sesion cerrada ni reemplazar otra cuenta.

Verificacion: `node tests/frontend_profile.cjs`. Pruebas adicionales del backend:

```powershell
Get-Content tests/profile_stability.py -Raw | docker compose exec -T user-service python -
python -X utf8 tests/smoke_profile.py
```

Ver [evidencias y limites del perfil](../docs/frontend/perfil.md). La demostracion
completa y revision automatizada de teclado/accesibilidad estan disponibles en
[el guion visual](../docs/frontend/demostracion-visual.md). Incluye instalacion de
axe como herramienta de pruebas y el comando `node tests/frontend_journey.cjs`.

Para la ampliacion opcional de consola, vaciado, lectores de pantalla orientados
por nombres/roles, zoom 200% y motores adicionales:

```powershell
$env:BROWSER_CHANNEL = "msedge"
$env:BROWSER_ENGINES = "chromium,firefox,webkit"
node tests/frontend_visual_optional.cjs
```

El resultado queda en `docs/frontend/pruebas-compatibilidad.json`. Axe, teclado,
landmarks y nombres accesibles se automatizan; la certificacion manual con NVDA,
VoiceOver o TalkBack sigue requiriendo un operador en el sistema correspondiente.

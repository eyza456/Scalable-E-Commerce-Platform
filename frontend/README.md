# Frontend Nexo

Propuestas visuales generadas con Google Stitch para el backend existente.
Proyecto Stitch: `3316878412824520653` (Ecommerce Microservices - Frontend MVP).
Nombre Nexo provisional; no representa una marca definitiva.

## Aplicacion conectada

`app/` contiene registro, inicio de sesion, consulta de la cuenta autenticada,
cierre local de sesion, catalogo con filtros por nombre/categoria/disponibilidad,
paginacion y detalle. Los productos, precios y stock vienen del backend real.
No se crean datos de demostracion al arrancar.

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

## Recorrido a implementar

1. Registro e inicio de sesion: integrados en `app/`.
2. Catalogo, categorias y detalle: integrados en `app/`.
3. Carrito: `/api/cart`.
4. Checkout y consulta del pedido: `/api/orders`.
5. Pago simulado: `/api/payments`; aprobado o rechazado, con reintento permitido.
6. Historial y cancelacion segun estado: `/api/orders`.
7. Consulta de cuenta integrada; edicion de perfil y renovacion del token pendientes.

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

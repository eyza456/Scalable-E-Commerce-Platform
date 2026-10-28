# API Gateway

El gateway Nginx esta integrado en Docker Compose y escucha en `http://localhost:8000`. Retira el prefijo `/api` antes de enviar la solicitud al servicio correspondiente.

| Ruta publica | Destino interno |
| --- | --- |
| `/api/auth/...` | `user-service:8000/auth/...` |
| `/api/users/...` | `user-service:8000/users/...` |
| `/api/products/...` | `product-service:8000/products/...` |
| `/api/categories/...` | `product-service:8000/categories/...` |
| `/api/cart/...` | `cart-service:8000/cart/...` |
| `/api/orders/...` | `order-service:8000/orders/...` |
| `/api/payments/...` | `payment-service:8000/payments/...` |

Notification Service sigue consumiendo eventos por la red interna. No se publican sus endpoints ni los de inventario y coordinacion interna.

## Arranque

```powershell
docker compose up -d --build
docker compose exec api-gateway nginx -t
```

Con los servicios existentes ya activos, para actualizar solo el gateway:

```powershell
docker compose up -d --no-deps --build api-gateway
```

`GET /` lista las rutas disponibles. `GET /health` comprueba el proceso Nginx, no la disponibilidad de toda la plataforma. Un servicio caido no impide arrancar el gateway ni consultar otras rutas.

## Ejemplos

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/users/me
PUT  /api/users/me
GET  /api/products/?name=laptop&category_id=1&available=true&limit=20
GET  /api/categories
POST /api/cart/items
GET  /api/cart
POST /api/orders
GET  /api/orders?status=PENDING&limit=20
POST /api/orders/123/cancel
POST /api/payments
GET  /api/payments/transactions/TX-...
```

Las operaciones protegidas requieren `Authorization: Bearer <token>`. Se conservan JWT, metodo, cuerpo JSON, filtros y estados de respuesta. La validacion de identidad y permisos continua en cada servicio. El gateway no otorga permisos adicionales.

Los redireccionamientos por barra final mantienen `/api`, el host y el puerto externo; por ejemplo `/api/products` redirige a `/api/products/`.

## Operacion

- `/api/orders/internal/...`, `/api/payments/internal/...` y rutas no declaradas devuelven 404. Se elimina el encabezado `X-Internal-Service-Key` de las solicitudes publicas; el gateway no necesita la clave interna.
- Se agrega `X-Request-ID` para correlacionar logs. Los encabezados de IP reenviada se construyen desde la conexion real.
- Fallos de conexion o timeouts del proxy devuelven 503 JSON. Los errores de la aplicacion conservan estado y contenido.
- No se repiten automaticamente solicitudes tras errores de red: una compra podria haberse guardado antes de perder la respuesta.
- DNS se renueva en la red Docker cada cinco segundos para admitir cambios de IP sin reiniciar el gateway.
- Cuerpo maximo: 1 MiB. Timeout de conexion: tres segundos; lectura/escritura: 30 segundos.

## Alcance local

`GATEWAY_PORT` cambia el puerto publicado, por defecto 8000. El gateway se publica en loopback para desarrollo local. Se conservan los puertos anteriores de los servicios para depuracion, por lo que no se obliga a que todo acceso local pase por el gateway.

Las llamadas entre servicios mantienen sus nombres internos. No se necesitan migraciones. TLS, acceso desde otras maquinas, CORS y limitacion de solicitudes se configuraran al definir el despliegue productivo.

## Pruebas

```powershell
python -X utf8 tests/gateway_stability.py
python -X utf8 tests/gateway_resilience.py
```

Las diez pruebas HTTP cubren salud, rutas, autenticacion, rutas internas bloqueadas, filtros, redirects y una compra completa, incluyendo perfil, categorias, carrito, historial y cancelacion. Limpian sus propios datos al finalizar correctamente; conservan una compra incompleta para diagnostico.

La prueba de resiliencia usa contenedores y una red Docker propios. Comprueba arranque sin backend, metodo/cuerpo/query/encabezados reenviados, retirada de la clave interna y recuperacion tras recrear el backend con otra IP. No detiene servicios reales y elimina sus recursos al terminar.

Para otro puerto, definir `GATEWAY_URL`, por ejemplo `http://127.0.0.1:8080`. La prueba aislada asigna su propio puerto temporal.

Referencias: [proxy de Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) y [rutas y DNS](https://nginx.org/en/docs/http/ngx_http_core_module.html).

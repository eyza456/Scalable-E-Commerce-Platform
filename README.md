# 🛒 E-Commerce Microservices Architecture

Revision del backend: [cambios de estabilizacion, pruebas y limites pendientes](docs/estabilizacion.md).

Flujo de pagos actualizado: [reserva de inventario y recuperacion automatica](docs/reservas-inventario.md).

Catalogo actualizado: [categorias, busqueda y filtros](docs/catalogo.md).

Usuarios: [actualizacion del perfil](docs/perfil-usuario.md).

Pedidos: [historial y cancelacion con liberacion de reservas](docs/pedidos.md).

Entrada central: [API Gateway, rutas y pruebas](docs/api-gateway.md) en `http://localhost:8000`.

Auditoria del 28/10/2026: [matriz completa de requisitos y resultados de la suite](docs/auditoria/matriz-requisitos.md).

Plataforma escalable de comercio electrónico basada en una arquitectura de microservicios, desarrollada con Python (FastAPI/SQLAlchemy), PostgreSQL, Redis, RabbitMQ y Docker Compose.

---

## 📐 Arquitectura del Sistema

```text
                               +-------------------+
                               |    API Gateway    |
                               |    (Puerto 8000)  |
                               +---------+---------+
                                         |
         +-----------------+-------------+-------------+-----------------+
         |                 |                           |                 |
+--------v-------+ +-------v--------+         +--------v-------+ +-------v--------+
|  User Service  | | Product Service|         | Cart Service   | | Order Service  |
|  (Puerto 8001) | | (Puerto 8002)  |         | (Puerto 8003)  | | (Puerto 8004)  |
+--------+-------+ +-------+--------+         +--------+-------+ +-------+--------+
         |                 |                           |                 |
         |                 |                           |         +-------v--------+
         |                 |                           |         | Payment Service|
         |                 |                           |         | (Puerto 8005)  |
         |                 |                           |         +-------+--------+
         |                 |                           |                 |
+--------v-----------------v---------------------------v-----------------v--------+
|                          Infraestructura & Middleware                          |
|  [PostgreSQL: 5432]     [Redis (Cache/Cart): 6379]   [RabbitMQ (Broker): 5672]  |
+---------------------------------------------------------------------------------+
```

---

## 📦 Estructura del Proyecto

```text
ecommerce-microservices/
├── gateway/                    # API Gateway (Enrutamiento centralizado)
├── infrastructure/             # Scripts de infraestructura y monitoreo
│   ├── monitoring/             # Configuraciones Prometheus / Grafana
│   └── scripts/                # Scripts SQL y de inicialización
│       └── init-dbs.sql
├── services/                   # Microservicios
│   ├── user-service/           # Gestión de usuarios y autenticación (JWT)
│   │   └── app/
│   │       ├── core/           # Configuración base, seguridad y DB
│   │       ├── models/         # Modelos SQLAlchemy / ORM
│   │       ├── schemas/        # Esquemas de validación Pydantic
│   │       ├── repositories/   # Capa de acceso a datos (Patrón Repository)
│   │       ├── services/       # Lógica de negocio
│   │       └── routers/        # Controladores y endpoints FastAPI
│   ├── product-service/        # Catálogo de productos e inventario
│   ├── order-service/          # Gestión de órdenes y pedidos
│   ├── cart-service/           # Carrito de compras (Redis)
│   └── payment-service/        # Pagos simulados y coordinacion de inventario
├── .env                        # Variables de entorno locales
├── .gitignore                  # Reglas de exclusión para Git
├── docker-compose.yml          # Orquestación de contenedores Docker
└── README.md                   # Documentación principal del proyecto
```

---

## 🚀 Puertos y Servicios

| Servicio | Puerto Host | Descripción | Tecnología |
| :--- | :--- | :--- | :--- |
| **API Gateway** | `8000` | Punto de entrada unificado para clientes | Nginx |
| **User Service** | `8001` | Autenticación, Usuarios y Roles | FastAPI + PostgreSQL (`user_db`) |
| **Product Service** | `8002` | Catálogo de Productos y Categorías | FastAPI + PostgreSQL (`product_db`) |
| **Order Service** | `8004` | Gestión y Estados de Pedidos | FastAPI + PostgreSQL (`order_db`) |
| **Cart Service** | `8003` | Carrito de Compras en tiempo real | FastAPI + Redis |
| **Payment Service** | `8005` | Procesamiento e historial de Pagos | FastAPI + PostgreSQL (`payment_db`) |
| **PostgreSQL** | `5432` a `5435` | Cuatro bases de datos en contenedores separados | PostgreSQL 16 |
| **Redis** | `6379` | Almacenamiento en caché y estado de carrito | Redis 7 |
| **RabbitMQ** | `5672` / `15672` | Broker de mensajes asíncronos y panel UI | RabbitMQ 3 Management |

---

## 🛠️ Requisitos Previos

Asegúrate de tener instalados los siguientes componentes en tu sistema:

- **Docker Desktop** (con Docker Compose v2+)
- **Git**
- **Python 3.11+** (para las pruebas desde el host; opcional para el arranque con Docker)

---

## ⚙️ Configuración e Instalación

### 1. Clonar el Repositorio
```bash
git clone <repository-url>
cd ecommerce-microservices
```

### 2. Configurar variables de entorno

`.env` no se versiona. Crear el archivo a partir de la plantilla:

```powershell
Copy-Item .env.example .env
```

Editar `.env` y reemplazar todos los valores `replace-me` y `replace-with-...`: las cuatro contrasenas PostgreSQL, `SECRET_KEY` e `INTERNAL_SERVICE_KEY`. Usar claves aleatorias independientes de al menos 32 caracteres para JWT y comunicacion interna. Para las contrasenas PostgreSQL usar letras, numeros, guion y guion bajo: se interpolan en una URL de conexion. Los nombres de base/usuario de la plantilla sirven para desarrollo. Todos los servicios deben compartir la misma clave JWT y la misma clave interna.

El puerto del gateway se configura con `GATEWAY_PORT` (8000 por defecto); Redis usa `REDIS_PORT`. Los demas puertos de la tabla deben estar libres. Las credenciales RabbitMQ son las predeterminadas de su imagen de desarrollo (`guest` / `guest`).

Comprobar la configuracion sin imprimir secretos:

```powershell
docker compose config --quiet
```

### 3. Construir y preparar la infraestructura

Desde la raiz del proyecto:

```powershell
docker compose build
docker compose up -d --wait --wait-timeout 180 user-db product-db order-db payment-db redis rabbitmq
```

Los healthchecks comprueban las cuatro bases, Redis y RabbitMQ. Si un comando falla, revisar `docker compose ps` y los logs del servicio antes de continuar.

### 4. Migrar el catalogo antes del arranque

Con la infraestructura disponible y los servicios de aplicacion aun detenidos:

```powershell
docker compose run --rm --no-deps product-service alembic upgrade head
docker compose run --rm --no-deps product-service alembic current
```

La revision actual debe ser `b1c5a09e3d72 (head)`. Repetir `upgrade head` es seguro. Product usa Alembic para crear productos, categorias, reservas, cancelaciones y registro de eventos.

En una instalacion nueva, User, Order y Payment crean sus tablas actuales al arrancar mediante SQLAlchemy; no necesitan ejecutar los SQL historicos. Esos SQL actualizan instalaciones existentes y se explican en los documentos de cada funcionalidad. `create_all` no migra tablas antiguas. No aplicar indiscriminadamente todas las migraciones historicas (por ejemplo Payment 002 fue sustituida por 003).

### 5. Arrancar y comprobar los servicios

```powershell
docker compose up -d
docker compose ps
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/products/health
Invoke-RestMethod http://localhost:8000/api/products/
```

El gateway debe devolver `status: healthy` y el catalogo nuevo una lista vacia. El arranque HTTP puede tardar unos segundos despues de `up -d`. Para consultar logs:

```powershell
docker compose logs --tail 100
```

Pruebas funcionales completas (requieren Python 3.11+ en el host; los tests de servicios se ejecutan dentro de Docker):

```powershell
powershell -ExecutionPolicy Bypass -File tests/run_stability.ps1
```

### 6. Repetir la verificacion desde cero sin afectar datos locales

```powershell
python -X utf8 tests/fresh_install.py
```

Esta prueba copia solo archivos versionados a una carpeta temporal, genera credenciales independientes, construye las imagenes y ejecuta los pasos anteriores en un proyecto Compose unico. Usa cuatro volumenes nuevos y puertos aleatorios; comprueba migraciones, tablas, seis servicios, una compra por gateway, consumidores y persistencia tras reiniciar. Al finalizar elimina exclusivamente sus contenedores, imagenes de servicio y volumenes de prueba. Conserva el informe en `docs/auditoria/instalacion-desde-cero.json`; el log local es `docs/auditoria/instalacion-desde-cero.log`.

## 🗄️ Bases de datos y persistencia

Docker Compose ejecuta cuatro PostgreSQL independientes con sus propios volumenes. Las bases se crean mediante `POSTGRES_DB` al iniciar un volumen nuevo. Las URLs de conexion seleccionan explicitamente `postgresql+psycopg2`, el controlador instalado en los cuatro servicios. El script SQL de `infrastructure/scripts/` es una referencia y no esta montado en el Compose actual. El gateway no requiere migraciones.

Para detener manteniendo los datos: `docker compose down`. Un siguiente arranque reutiliza los volumenes. No usar `down -v` para actualizar una instalacion con datos.

---

## 🌐 Panel de Gestión de RabbitMQ

Puedes acceder a la consola de administración de RabbitMQ navegando a:
- **URL**: `http://localhost:15672`
Usa las credenciales de tu entorno local; no se versionan.

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT.

## Cierre de hallazgos de auditoria

### Frontend visual Nexo

La interfaz de registro, inicio de sesion, catalogo y detalle ya consulta el backend
mediante el API Gateway. Con el backend configurado y sus migraciones aplicadas:

```powershell
docker compose -f docker-compose.yml -f compose.frontend.yml up -d --build frontend
```

Abrir `http://127.0.0.1:8080/`. Carrito, pedidos y pagos siguen pendientes de
integracion visual. La galeria de Stitch en el puerto 5173 es una referencia con
datos ficticios. Ver [alcance, arranque y pruebas del frontend](frontend/README.md).
Este complemento es posterior a la evidencia de instalacion limpia del backend;
su verificacion especifica esta en `docs/frontend/integracion.json`.

Se corrigieron la concurrencia del carrito, los pedidos duplicados, la revalidacion del catalogo, los limites de registro y la fecha final de pagos. Consultar [contrato HTTP, migraciones y pruebas](docs/auditoria/cierre-hallazgos.md).

Los pagos simulados tambien permiten rechazos por fondos insuficientes, tarjeta vencida y rechazo del emisor. Ver [uso y pruebas](docs/pagos-simulados.md).

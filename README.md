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
- **Python 3.11+** (opcional, para desarrollo local sin Docker)

---

## ⚙️ Configuración e Instalación

### 1. Clonar el Repositorio
```bash
git clone <repository-url>
cd ecommerce-microservices
```

### 2. Configurar Variables de Entorno
El archivo `.env` ya incluye los valores predeterminados para desarrollo local. Si deseas ajustar contraseñas o puertos:

```bash
# Editar el archivo .env si es necesario
cat .env
```

### 3. Levantar los Servicios con Docker Compose
Para iniciar todos los servicios e infraestructura en segundo plano:

```bash
docker compose up -d --build
```

Para verificar el estado de los contenedores:
```bash
docker compose ps
```

Para ver los logs en tiempo real de todos los microservicios:
```bash
docker compose logs -f
```

---

## 🗄️ Inicialización de Bases de Datos

Docker Compose ejecuta cuatro contenedores PostgreSQL independientes para `user_db`, `product_db`, `order_db` y `payment_db`, cada uno con su propio volumen. Las bases se crean mediante `POSTGRES_DB` al iniciar un volumen nuevo.

Product Service usa Alembic. Antes de utilizar una instalacion nueva, ejecutar:

```bash
docker compose exec product-service alembic upgrade head
```

Para instalaciones con datos existentes, seguir las migraciones descritas en los documentos de cada funcionalidad. El gateway no requiere migraciones. El script SQL de `infrastructure/scripts/` se conserva como referencia y no esta montado en el Compose actual.

---

## 🌐 Panel de Gestión de RabbitMQ

Puedes acceder a la consola de administración de RabbitMQ navegando a:
- **URL**: `http://localhost:15672`
Usa las credenciales de tu entorno local; no se versionan.

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT.

## Cierre de hallazgos de auditoria

Se corrigieron la concurrencia del carrito, los pedidos duplicados, la revalidacion del catalogo, los limites de registro y la fecha final de pagos. Consultar [contrato HTTP, migraciones y pruebas](docs/auditoria/cierre-hallazgos.md).

Los pagos simulados tambien permiten rechazos por fondos insuficientes, tarjeta vencida y rechazo del emisor. Ver [uso y pruebas](docs/pagos-simulados.md).

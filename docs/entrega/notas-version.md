# Notas de version - v0.1.0-rc.1

Primera version etiquetada del backend MVP. Baseline auditado: 47c5085; correcciones de concurrencia/checkout/entradas/fecha: f2103d7; rechazos simulados: d2231bc; instalacion limpia: 5227fb3.

## Incluido

- Registro/login JWT, perfil y permisos por rol; correo hasta 254 y contrasenas limitadas por bytes UTF-8 sin truncamiento.
- Catalogo, categorias, busqueda y filtros; inventario reservado atomicamente y eventos idempotentes.
- Carrito con mutaciones Redis atomicas; checkout durable por version, revalidacion de catalogo y recuperacion sin duplicar pedidos.
- Historial privado, cancelacion y liberacion coordinada de reservas; transiciones administrativas restringidas.
- Pagos simulados aprobados/rechazados por stock, fondos insuficientes, tarjeta vencida o emisor; motivo y fecha final persistidos.
- Gateway Nginx, bloqueo de rutas internas, recuperacion por DNS, Outbox, reintentos y DLQ.
- README corregido, healthchecks de infraestructura y controlador PostgreSQL explicito; instalacion limpia comprobada.
- Matriz actualizada, auditoria historica preservada y demostracion reproducible de nueve pasos.

## Validacion

124 unittest aprobados sin fallos, pruebas HTTP, migracion, TTL/DLQ, resiliencia de gateway y demostracion de entrega. Instalacion independiente desde volumenes nuevos con compra/eventos y persistencia tras reiniciar.

## Limites de esta RC

69 requisitos cumplidos, 8 parciales y 1 pendiente. Rendimiento requiere objetivos y carga; escalabilidad multinstancia y otros hosts no estan verificados. Redis/RabbitMQ no garantizan durabilidad al recrear contenedores; /health de aplicaciones es principalmente liveness. Notificaciones por consola, cobros simulados y administracion de roles incompleta. Ver pendientes.md antes de exponer la plataforma o afirmar disponibilidad productiva.

# Verificacion de instalacion desde cero

Resultado final: **APROBADO, codigo de salida 0**, el 28 de octubre de 2026.

Se verifico el flujo del README usando una copia de los archivos versionados con el contenido actual, sin copiar el .env local, caches, respaldos ni bases existentes. Se construyeron las siete imagenes de servicios/gateway desde esa copia. Se generaron credenciales independientes y se usaron un proyecto Compose UUID, cuatro volumenes PostgreSQL nuevos y un puerto dinamico de gateway. Se quitaron los nombres fijos de contenedores y los puertos adicionales exclusivamente en la configuracion de prueba para convivir con la instalacion habitual.

## Problemas encontrados y corregidos

1. El README suponia que .env venia incluido. Ahora indica copiar .env.example, reemplazar credenciales y validar Compose sin imprimir secretos.
2. La migracion del catalogo se documentaba despues del arranque de las aplicaciones. Ahora se construyen imagenes, se espera a la infraestructura y se ejecuta Alembic antes de iniciar los servicios.
3. Faltaban comprobaciones de disponibilidad en tres bases, Redis y RabbitMQ. Se agregaron healthchecks y dependencias con service_healthy, incluidos los consumidores de RabbitMQ.
4. Las URLs postgresql:// dejaban que SQLAlchemy eligiera el controlador. En una imagen nueva User y Order fallaron con ModuleNotFoundError: psycopg, pese a tener psycopg2-binary instalado. Las cuatro URLs ahora seleccionan postgresql+psycopg2:// explicitamente.

La prueba automatizada tambien consulta de nuevo el puerto dinamico del gateway despues del reinicio, porque Docker puede reasignarlo.

## Comprobaciones

- Docker Compose valido usando exclusivamente la plantilla y credenciales nuevas.
- Construccion de siete imagenes; infraestructura disponible antes de iniciar las aplicaciones.
- Alembic upgrade head desde base vacia y repetido sin cambios; revision b1c5a09e3d72 (head).
- Trece contenedores activos y cero reinicios inesperados en el arranque inicial; health HTTP de seis servicios y del gateway.
- Tablas y columnas actuales en las cuatro bases: categorias, reservas, barreras de cancelacion, checkout durable, Outbox, motivos de rechazo y fecha final del pago. Se verifican tablas vacias antes del primer registro, correo VARCHAR(254) e indice unico sin distinguir mayusculas.
- Registro y login por gateway; creacion de categoria y producto con token administrativo efimero de prueba; carrito y pedido.
- Rechazo por fondos insuficientes sin descuento de stock; nuevo intento aprobado.
- Pedido PAID, reserva CONSUMED, tres entregas Outbox PUBLISHED y notificacion recibida.
- Reinicio del proyecto y persistencia de usuario, catalogo, pedido, fecha del pago y carrito Redis; stock sin segundo descuento.
- Eliminacion exclusiva del proyecto de prueba, sus imagenes y volumenes; instalacion habitual conservada.

## Reproducir

Desde la raiz, con Docker Desktop y Python 3.11+:

```powershell
python -X utf8 tests/fresh_install.py
```

La prueba usa solo la biblioteca estandar de Python. No requiere instalar las dependencias del backend en Windows. Los comandos de instalacion manual estan en [README](../../README.md). Para actualizar una base existente se mantienen los procedimientos propios de cada servicio; esta prueba no valida migrar datos historicos arbitrarios.

Resultado verificable: [instalacion-desde-cero.json](instalacion-desde-cero.json). El JSON incluye el hash del README probado, el identificador de proyecto, los nombres de sus volumenes y las comprobaciones completadas. Log local: instalacion-desde-cero.log (excluido de Git).

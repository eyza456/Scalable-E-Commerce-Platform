# Perfil local multinstancia

El overlay `compose.multinstance.yml` permite ejecutar replicas de los seis
microservicios con la infraestructura compartida de su propio proyecto Compose.
Requiere Docker Compose >=2.24.4 (`!reset` y `!override`). No implementa
autoscaling, alta disponibilidad de bases de datos ni Kubernetes.

## Arranque reproducible

Crear un archivo de entorno independiente a partir de `.env.example` con los
secretos reemplazados, siguiendo el README principal. No copiar las credenciales
del entorno habitual. Para un proyecto nuevo llamado `ecommerce-replicas`:

```powershell
$replicaCompose = @('compose', '--project-name', 'ecommerce-replicas', '--env-file', '.env.replicas', '-f', 'docker-compose.yml', '-f', 'compose.frontend.yml', '-f', 'compose.multinstance.yml')
docker @replicaCompose config --quiet
docker @replicaCompose build
docker @replicaCompose up -d --wait --wait-timeout 180 user-db product-db order-db payment-db redis rabbitmq
docker @replicaCompose run --rm --no-deps product-service alembic upgrade head
docker @replicaCompose up -d
```

El primer arranque es con una instancia por servicio: actualmente algunos
servicios inicializan tablas al importar. Esperar a que cada `/health` responda
antes de escalar; la prueba automatizada realiza esa espera. Esto no demuestra
que la creacion inicial simultanea del esquema sea segura. No ejecutar
`--scale` sobre PostgreSQL, Redis o RabbitMQ.

```powershell
docker @replicaCompose up -d --no-recreate --scale user-service=2 --scale product-service=2 --scale cart-service=2 --scale order-service=2 --scale payment-service=2 --scale notification-service=2
docker @replicaCompose ps
docker @replicaCompose port api-gateway 80
docker @replicaCompose port frontend 80
docker @replicaCompose up -d --no-deps --no-recreate --scale order-service=3 order-service
```

Los puertos de cliente/gateway son aleatorios y de loopback por defecto. Abrir
la direccion que devuelve `port frontend 80`. Opcionalmente definir
`MULTI_FRONTEND_PORT` y `MULTI_GATEWAY_PORT` en el entorno independiente.
No se publican puertos de aplicaciones, bases, Redis ni RabbitMQ. Los nombres
de contenedores, volumenes y red pertenecen al proyecto; el Compose habitual
se conserva. Para detener este perfil, usar `docker @replicaCompose down`
sin borrar volumenes si se necesitan sus datos.

## Pruebas

```powershell
python tests/multinstance_independence.py
python tests/multinstance_load.py
```

Ambos runners esperan la disponibilidad HTTP de cada proceso nuevo antes de
enviar operaciones. `tests/multinstance.py` es su instrumento base; se recomienda
usar los dos comandos anteriores para la verificacion completa.

Cada runner crea una copia versionada con secretos nuevos, red/volumenes nuevos
y proyecto UUID, y elimina solo ese proyecto. No requiere modificar `.env` ni
detener la demo. No ejecutar ambas pruebas simultaneamente al medir rendimiento.
Los cambios nuevos deben estar al menos agregados a Git para entrar en la copia.

- [Resultado funcional](resultado.json): dos instancias de cada microservicio,
  salud de cada proceso y 20 contenedores. Checkout y pago reciben 12 solicitudes
  simultaneas dirigidas a ambas replicas, con un unico pedido/pago, una reserva
  consumida y un descuento de stock. Cuatro cancelaciones concurrentes terminan
  en CANCELLED. Pedidos escala 2/3/1/2 conservando los IDs de los otros servicios;
  catalogo y frontend siguen accesibles. El entorno habitual conserva IDs,
  tiempos de inicio y contadores de reinicio.
- [Carga multinstancia](carga/resultado.json): reutiliza el instrumento original,
  sus 100 productos, 20 usuarios, calentamiento y etapas de 1/5/10/20 usuarios.
  Conserva exactamente `tests/performance_goals.json`. El estado de este JSON
  determina si paso; no inferirlo de la prueba funcional. La medicion historica
  de una instancia permanece en `docs/rendimiento/`.
  La primera carga multinstancia aprobada tambien se conserva en
  [carga/inicial](carga/inicial/README.md), antes de ampliar el driver de disponibilidad.
- [Independencia completa](independencia.json): repite la prueba funcional y
  escala cada uno de los seis microservicios 2/3/1/2, espera la salud de todos
  sus procesos y verifica que los otros cinco conservan sus IDs.
  El driver escribe tambien `resultado.json` como alias de esa misma ejecucion;
  no se cuentan esos dos archivos como pruebas ejecutadas por separado.

## Limites de la evidencia

La carga multinstancia aprobo el perfil original: 18.235 solicitudes medidas.
0 errores y 1.052 compras contando el calentamiento. A 20 usuarios:

| Operacion | p95 observado | Limite p95 sin cambios |
| --- | ---: | ---: |
| Historial | 404,69 ms | 500 ms |
| Checkout | 1.121,53 ms | 1.500 ms |
| Pago | 911,85 ms | 2.000 ms |
| Compra completa | 3.161,80 ms | 10.000 ms |

Tambien aprobaron p99, muestras minimas, errores, throughput e invariantes.
El throughput util a 20 usuarios fue 98,89 solicitudes/s. Historial queda a
aproximadamente un 19% de su limite p95. No se infiere mejora frente a la
medicion historica de una instancia: es otro perfil con mas procesos en el
mismo host y se acredita capacidad multinstancia local, no ganancia lineal.

No se prueba caida abrupta de replicas durante un pago, reparto uniforme de
solicitudes en Nginx, redelivery de notificaciones sin duplicados, durabilidad
de Redis/RabbitMQ al recrearlos, particiones de red ni otro sistema operativo.
La notificacion unica observada es una entrega normal: el consumidor imprime
el evento y no tiene una deduplicacion durable. RNF-05/06 se refieren a capacidad
multinstancia local; no constituyen una garantia de entrega exactamente una vez
ni una demostracion de mejora de rendimiento con replicas.

Los hashes de fuentes, fecha, limpieza y referencia Git viven en los JSON.
`source_commit` identifica el HEAD al preparar la prueba; los hashes identifican
los bytes copiados, incluidos los archivos nuevos agregados a Git antes del
commit de cierre. El manifiesto contrasta esos hashes con las fuentes entregadas.
Los logs locales estan excluidos de Git porque incluyen detalle operativo.
El primer intento de independencia se conserva en
[intentos/independencia-arranque.json](intentos/independencia-arranque.json):
el verificador no espero la disponibilidad HTTP de un proceso nuevo. Se corrigio
la espera del driver, se limpio su proyecto y se repitio la prueba.

# Rendimiento tras optimizar Outbox

**Resultado: OBJETIVOS NO CUMPLIDOS.**

Se repitio la misma prueba: objetivos JSON, generador, calculo de metricas y preparacion de entorno con hashes identicos a la linea base. No se relajo ningun umbral. [Linea base preservada](../baseline-9b6eeb3/README.md) y [objetivos](objetivos.md).

## Cambio y garantias

El worker continua inmediatamente despues de publicar y confirmar en PostgreSQL un lote completo de 50 entregas. Mantiene la espera de cinco segundos si el lote queda incompleto, falla una entrega o hay excepcion de DB. No cambia polling en vacio, limites del lote, SQL, skip_locked, confirmaciones RabbitMQ, identificadores ni semantica de entrega al menos una vez.

Las cinco pruebas nuevas verifican drenaje de 120 entregas antes de esperar, backoff con fallo parcial, ausencia de bucle ante DB caida, dos workers con filas bloqueadas y recuperacion tras fallar el commit despues del ACK. Este ultimo caso puede reenviar el mismo ID; se conserva la necesidad de consumidores idempotentes.

## Comparacion a 20 usuarios

| Metrica | Antes | Despues | Objetivo |
| --- | ---: | ---: | ---: |
| Compra p95 (s) | 10.839 | 10.203 | <=10 |
| Compra p99 (s) | 11.104 | 10.673 | <=15 |
| Solicitudes utiles/s | 41.30 | 37.62 | >=20 |
| Errores HTTP inesperados (%) | 0.00 | 0.00 | <1 |
| Compras medidas a 20 usuarios | 170 | 155 | >=100 |

Reduccion observada de p95: **5.87%**. Es una comparacion de dos ejecuciones locales, no una demostracion de causalidad exclusiva ni una estimacion de capacidad productiva.

## Etapas de la nueva ejecucion

| Usuarios | Segundos reales | HTTP | HTTP/s total | HTTP/s util | Errores (%) | Compra p95 (s) | Compra p99 (s) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 63.39 | 334 | 5.27 | 3.28 | 0.00 | 5.316 | 5.316 |
| 5 | 65.15 | 1458 | 22.38 | 13.26 | 0.00 | 7.609 | 8.145 |
| 10 | 66.36 | 2676 | 40.33 | 24.78 | 0.00 | 6.162 | 6.366 |
| 20 | 67.20 | 4199 | 62.48 | 37.62 | 0.00 | 10.203 | 10.673 |

## Todos los objetivos de latencia a 20 usuarios

| Operacion | Muestras | p50 (ms) | p95 (ms) | p99 (ms) | Limite p95/p99 (ms) | Estado |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| catalog | 477 | 27.51 | 119.83 | 172.65 | 500/1000 | Cumple |
| product | 477 | 23.85 | 132.81 | 176.67 | 500/1000 | Cumple |
| profile | 477 | 16.56 | 59.26 | 90.33 | 500/1000 | Cumple |
| history | 477 | 151.40 | 455.55 | 858.16 | 500/1000 | Cumple |
| cart_read | 155 | 16.48 | 199.45 | 220.10 | 500/1000 | Cumple |
| cart_add | 155 | 70.55 | 227.60 | 264.72 | 1500/3000 | Cumple |
| checkout | 155 | 750.94 | 1313.03 | 2018.91 | 1500/3000 | Cumple |
| payment | 155 | 432.41 | 1031.39 | 1274.25 | 2000/5000 | Cumple |
| purchase_flow | 155 | 7482.68 | 10203.14 | 10672.84 | 10000/15000 | No cumple |

## Integridad

8667 solicitudes HTTP medidas; 0 errores inesperados. Compras totales contando calentamiento: 341. Integridad: APROBADA.

Pagos: {'paid': 341, 'other': 0, 'duplicate_orders': 0, 'published': 1023}. Pedidos: {'paid': 341, 'other': 0, 'unfinished_checkouts': 0}. Inventario: {'stock': 999659, 'consumed': 341, 'other': 0, 'processed_events': 341}.

## Entorno y recursos

Host Windows-11-10.0.26200-SP0; Docker 29.7.2, 8 CPU y 7.66 GiB. Contenedores adicionales activos: antes 20, despues 20. Generador y servicios comparten equipo. Versiones de dependencias iguales: True. Versiones medidas: {'python': '3.12.16', 'fastapi': '0.162.0', 'sqlalchemy': '2.1.6', 'uvicorn': '0.54.0', 'httpx': '0.28.1', 'pika': '1.4.4', 'psycopg2-binary': '2.9.13'}.

CPU 100 % representa aproximadamente un nucleo. Se muestrea cada cinco segundos mas el tiempo de docker stats; los maximos no necesariamente coinciden. No hay limites de recursos por servicio.

| Servicio | CPU media (%) | CPU maxima (%) | RAM maxima (MiB) | Muestras |
| --- | ---: | ---: | ---: | ---: |
| rabbitmq | 40.07 | 157.68 | 211.90 | 36 |
| order-service | 43.94 | 137.45 | 138.40 | 36 |
| payment-service | 20.86 | 134.42 | 166.20 | 36 |
| product-service | 18.54 | 57.98 | 103.30 | 36 |
| order-db | 9.66 | 41.71 | 57.65 | 36 |
| cart-service | 8.35 | 35.78 | 119.40 | 36 |
| payment-db | 5.12 | 27.27 | 48.52 | 36 |
| api-gateway | 3.81 | 24.10 | 9.46 | 36 |
| product-db | 4.96 | 23.04 | 45.26 | 36 |
| user-service | 6.77 | 21.82 | 92.11 | 36 |
| user-db | 3.91 | 19.71 | 44.03 | 36 |
| redis | 2.37 | 10.47 | 8.52 | 36 |
| notification-service | 0.37 | 1.02 | 39.91 | 36 |

## Alcance y reproducibilidad

Carga cerrada a 1/5/10/20 usuarios, 60 segundos programados por etapa y 15 segundos de calentamiento excluido. La duracion real incluye ciclos en curso. Preparacion, registro y login fuera de la medida. Catalogo de 100 productos; paginas de 20; compra de un producto compartido con stock suficiente; historiales pequenos que crecen por etapa. Los sondeos quedan fuera del throughput util; la compra termina al observar PAID. Integridad de inventario y eventos se verifica despues de drenar pendientes.

No demuestra sostenibilidad durante horas, saturacion, tasas abiertas de llegada, grandes bases, replicas, otros hosts ni SLA de produccion. Hay diferencias de carga externa no controladas entre ejecuciones. Las dependencias no estan fijadas, aunque se registran y comparan versiones. La instalacion habitual no se modifica por el benchmark y el proyecto aislado se elimina al terminar.

```powershell
python -X utf8 tests/performance_metrics_test.py
python -X utf8 tests/performance_load.py
python -X utf8 tests/performance_report.py
```

[Resultado](resultado.json), [CSV](metricas.csv), [muestras](resultado-muestras.jsonl), [recursos](resultado-recursos.json), [recursos resumidos](recursos-resumen.json), [comparacion JSON](comparacion-outbox.json), [hashes](evidencias.json), [linea base completa](../baseline-9b6eeb3/informe.md). Log local: ejecucion.log. La etiqueta v0.1.0-rc.1 permanece intacta.

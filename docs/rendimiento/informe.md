# Rendimiento tras perfilar SQL y reutilizar conexiones HTTP

> **Repetición final con entorno controlado (2 de noviembre de 2026):** se aplicaron los índices de historial y pagos, se detuvieron temporalmente la instancia normal y Kubernetes, y se repitió el benchmark con los mismos objetivos. A 20 usuarios el historial quedó en p95 354,46 ms/p99 461,47 ms, checkout en p95 1400,64 ms/p99 1895,93 ms, pago en p95 1960,37 ms/p99 4174,85 ms y compra en p95 6,546 s. La prueba registró 0% de errores, invariantes correctas y todos los objetivos aprobados.

**Resultado: APROBADO para el perfil local controlado.**

Se repitio la misma prueba: objetivos JSON, generador, calculo de metricas y preparacion de entorno con hashes identicos a la linea base. No se relajo ningun umbral. [Linea base preservada](baseline-1a8d097/README.md) y [objetivos](objetivos.md).

## Cambio y garantias

Order, Payment y Cart comparten un pool HTTP por proceso, con clientes efimeros para aislar encabezados y cookies por llamada. Se reutiliza el transporte y su contexto TLS/conexiones; se mantienen timeouts por llamada, validacion TLS, ausencia de reintentos automaticos y las transacciones/bloqueos de negocio. El pool se cierra al apagar el servicio. El historial valida y copia el mismo modelo publico en el worker, libera la transaccion de lectura y renderiza JSON antes de volver al event loop; no omite la validacion del esquema ni el filtro por propietario. Outbox permanece como en la linea base, con ACK por mensaje, espera de un segundo en vacio y backoff de cinco segundos ante error.

Seis pruebas del pool se ejecutan en cada uno de los tres servicios: transporte reutilizado, aislamiento de tokens/cookies, concurrencia, timeouts/estados preservados, POST sin reintento y cierre/reapertura. Se conservan las pruebas de Outbox, checkout idempotente, revalidacion de stock/precio y cancelacion. Se agregó el índice compuesto de historial mediante migración versionada; no se ampliaron los pools SQL para conseguir el resultado. Los planes se capturaron con EXPLAIN ANALYZE/BUFFERS.

El diagnostico SQL/HTTP antes y despues se documenta en [perfilado](../perfilado/informe.md). Es una corrida instrumentada separada, de 30 segundos, que no se usa para aprobar latencias. Los numeros de este informe corresponden al benchmark original sin instrumentacion, a 1/5/10/20 usuarios durante 60 segundos por etapa y objetivos intactos.

## Comparacion a 20 usuarios

| Metrica | Antes | Despues | Objetivo |
| --- | ---: | ---: | ---: |
| Compra p95 (s) | 8.205 | 6.546 | <=10 |
| Compra p99 (s) | 10.702 | 7.400 | <=15 |
| Solicitudes utiles/s | 58.47 | 85.68 | >=20 |
| Errores HTTP inesperados (%) | 0.00 | 0.00 | <1 |
| Compras medidas a 20 usuarios | 221 | 323 | >=100 |

Reduccion observada de p95 de compra frente a la línea base: **52.21%**. Es una comparacion de dos ejecuciones locales, no una demostracion de causalidad exclusiva ni una estimacion de capacidad productiva.

## APIs objetivo: antes y despues

| Operacion p95 (ms) | Antes | Despues | Limite |
| --- | ---: | ---: | ---: |
| history | 804.31 | 354.46 | 500 |
| checkout | 2894.15 | 1400.64 | 1500 |
| payment | 2488.61 | 1960.37 | 2000 |

## Etapas de la nueva ejecucion

| Usuarios | Segundos reales | HTTP | HTTP/s total | HTTP/s util | Errores (%) | Compra p95 (s) | Compra p99 (s) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 60.10 | 1006 | 16.74 | 14.47 | 0.00 | 1.919 | 2.298 |
| 5 | 60.82 | 3156 | 51.89 | 44.40 | 0.00 | 2.362 | 3.074 |
| 10 | 60.95 | 4415 | 72.44 | 62.40 | 0.00 | 3.515 | 4.698 |
| 20 | 60.91 | 6280 | 103.11 | 85.68 | 0.00 | 6.546 | 7.400 |

## Todos los objetivos de latencia a 20 usuarios

| Operacion | Muestras | p50 (ms) | p95 (ms) | p99 (ms) | Limite p95/p99 (ms) | Estado |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| catalog | 1425 | 19.47 | 97.27 | 220.92 | 500/1000 | Cumple |
| product | 1425 | 17.53 | 80.54 | 180.86 | 500/1000 | Cumple |
| profile | 1425 | 10.07 | 30.18 | 55.06 | 500/1000 | Cumple |
| history | 996 | 148.62 | 354.46 | 461.47 | 500/1000 | Cumple |
| cart_read | 323 | 14.87 | 148.93 | 295.86 | 500/1000 | Cumple |
| cart_add | 323 | 54.83 | 266.44 | 334.82 | 1500/3000 | Cumple |
| checkout | 323 | 677.09 | 1400.64 | 1895.93 | 1500/3000 | Cumple |
| payment | 323 | 538.40 | 1960.37 | 4174.85 | 2000/5000 | Cumple |
| purchase_flow | 323 | 3384.77 | 6546.15 | 7400.26 | 10000/15000 | Cumple |

## Integridad

16260 solicitudes HTTP medidas; 0 errores inesperados. Compras totales contando calentamiento: 920. Integridad: APROBADA.

Pagos: {'paid': 1051, 'other': 0, 'duplicate_orders': 0, 'published': 3153}. Pedidos: {'paid': 1051, 'other': 0, 'unfinished_checkouts': 0}. Inventario: {'stock': 998949, 'consumed': 1051, 'other': 0, 'processed_events': 1051}.

## Entorno y recursos

Host Windows-11-10.0.26200-SP0; Docker 29.9.2, 8 CPU y 7.66 GiB. La corrida controlada tuvo 5 contenedores adicionales del sistema; la instancia normal y Kubernetes se restauraron después. Generador y servicios comparten equipo. Versiones medidas: {'python': '3.12.16', 'fastapi': '0.162.0', 'sqlalchemy': '2.1.6', 'uvicorn': '0.54.0', 'httpx': '0.28.1', 'pika': '1.4.4', 'psycopg2-binary': '2.9.13'}.

CPU 100 % representa aproximadamente un nucleo. Se muestrea cada cinco segundos mas el tiempo de docker stats; los maximos no necesariamente coinciden. No hay limites de recursos por servicio.

| Servicio | CPU media (%) | CPU maxima (%) | RAM maxima (MiB) | Muestras |
| --- | ---: | ---: | ---: | ---: |
| rabbitmq | 37.03 | 141.06 | 202.80 | 32 |
| order-service | 63.49 | 116.20 | 84.96 | 32 |
| product-service | 45.14 | 78.42 | 101.50 | 32 |
| product-db | 11.23 | 72.83 | 48.45 | 32 |
| payment-service | 29.41 | 70.68 | 104.50 | 32 |
| order-db | 17.41 | 51.10 | 55.86 | 32 |
| user-service | 15.14 | 40.99 | 92.29 | 32 |
| user-db | 4.14 | 39.52 | 45.21 | 32 |
| cart-service | 15.27 | 34.46 | 80.45 | 32 |
| payment-db | 7.96 | 26.36 | 54.90 | 32 |
| api-gateway | 7.05 | 24.45 | 9.89 | 32 |
| redis | 4.46 | 22.09 | 15.77 | 32 |
| notification-service | 0.88 | 6.03 | 38.08 | 32 |

## Alcance y reproducibilidad

Carga cerrada a 1/5/10/20 usuarios, 60 segundos programados por etapa y 15 segundos de calentamiento excluido. La duracion real incluye ciclos en curso. Preparacion, registro y login fuera de la medida. Catalogo de 100 productos; paginas de 20; compra de un producto compartido con stock suficiente; historiales pequenos que crecen por etapa. Los sondeos quedan fuera del throughput util; la compra termina al observar PAID. Integridad de inventario y eventos se verifica despues de drenar pendientes.

No demuestra sostenibilidad durante horas, saturacion, tasas abiertas de llegada, grandes bases, replicas, otros hosts ni SLA de produccion. Hay diferencias de carga externa no controladas entre ejecuciones. Las dependencias no estan fijadas, aunque se registran y comparan versiones. La instalacion habitual no se modifica por el benchmark y el proyecto aislado se elimina al terminar.

```powershell
python -X utf8 tests/performance_metrics_test.py
python -X utf8 tests/performance_load.py
python -X utf8 tests/performance_report.py
```

[Resultado](resultado.json), [CSV](metricas.csv), [muestras](resultado-muestras.jsonl), [recursos](resultado-recursos.json), [recursos resumidos](recursos-resumen.json), [comparacion JSON](comparacion-sql-http.json), [hashes](evidencias.json), [linea base completa](baseline-1a8d097/informe.md). Log local: ejecucion.log. La etiqueta v0.1.0-rc.1 permanece intacta.

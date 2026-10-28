# Rendimiento tras perfilar SQL y reutilizar conexiones HTTP

**Resultado: OBJETIVOS NO CUMPLIDOS.**

Se repitio la misma prueba: objetivos JSON, generador, calculo de metricas y preparacion de entorno con hashes identicos a la linea base. No se relajo ningun umbral. [Linea base preservada](../baseline-1a8d097/README.md) y [objetivos](objetivos.md).

## Cambio y garantias

Order, Payment y Cart comparten un pool HTTP por proceso, con clientes efimeros para aislar encabezados y cookies por llamada. Se reutiliza el transporte y su contexto TLS/conexiones; se mantienen timeouts por llamada, validacion TLS, ausencia de reintentos automaticos y las transacciones/bloqueos de negocio. El pool se cierra al apagar el servicio. Outbox permanece como en la linea base, con ACK por mensaje, espera de un segundo en vacio y backoff de cinco segundos ante error.

Seis pruebas del pool se ejecutan en cada uno de los tres servicios: transporte reutilizado, aislamiento de tokens/cookies, concurrencia, timeouts/estados preservados, POST sin reintento y cierre/reapertura. Se conservan las pruebas de Outbox, checkout idempotente, revalidacion de stock/precio y cancelacion. No se agregaron indices ni se ampliaron los pools SQL para conseguir el resultado; los planes se capturaron con EXPLAIN ANALYZE/BUFFERS.

El diagnostico SQL/HTTP antes y despues se documenta en [perfilado](../../perfilado/informe.md). Es una corrida instrumentada separada, de 30 segundos, que no se usa para aprobar latencias. Los numeros de este informe corresponden al benchmark original sin instrumentacion, a 1/5/10/20 usuarios durante 60 segundos por etapa y objetivos intactos.

## Comparacion a 20 usuarios

| Metrica | Antes | Despues | Objetivo |
| --- | ---: | ---: | ---: |
| Compra p95 (s) | 8.205 | 5.824 | <=10 |
| Compra p99 (s) | 10.702 | 6.311 | <=15 |
| Solicitudes utiles/s | 58.47 | 72.73 | >=20 |
| Errores HTTP inesperados (%) | 0.00 | 0.00 | <1 |
| Compras medidas a 20 usuarios | 221 | 274 | >=100 |

Reduccion observada de p95: **29.02%**. Es una comparacion de dos ejecuciones locales, no una demostracion de causalidad exclusiva ni una estimacion de capacidad productiva.

## Etapas de la nueva ejecucion

| Usuarios | Segundos reales | HTTP | HTTP/s total | HTTP/s util | Errores (%) | Compra p95 (s) | Compra p99 (s) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 61.17 | 946 | 15.46 | 13.34 | 0.00 | 1.487 | 2.012 |
| 5 | 60.33 | 2233 | 37.01 | 31.63 | 0.00 | 4.220 | 4.437 |
| 10 | 60.96 | 3880 | 63.65 | 54.79 | 0.00 | 2.888 | 3.278 |
| 20 | 61.10 | 5263 | 86.13 | 72.73 | 0.00 | 5.824 | 6.311 |

## Todos los objetivos de latencia a 20 usuarios

| Operacion | Muestras | p50 (ms) | p95 (ms) | p99 (ms) | Limite p95/p99 (ms) | Estado |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| catalog | 837 | 34.79 | 246.71 | 293.71 | 500/1000 | Cumple |
| product | 837 | 33.67 | 222.17 | 305.03 | 500/1000 | Cumple |
| profile | 837 | 19.61 | 72.19 | 123.27 | 500/1000 | Cumple |
| history | 837 | 266.57 | 507.20 | 662.76 | 500/1000 | No cumple |
| cart_read | 274 | 15.12 | 132.61 | 217.65 | 500/1000 | Cumple |
| cart_add | 274 | 45.57 | 229.22 | 297.25 | 1500/3000 | Cumple |
| checkout | 274 | 783.30 | 1179.79 | 1376.13 | 1500/3000 | Cumple |
| payment | 274 | 522.03 | 1102.09 | 2102.53 | 2000/5000 | Cumple |
| purchase_flow | 274 | 3047.70 | 5823.82 | 6310.71 | 10000/15000 | Cumple |

## Incumplimientos que siguen abiertos

La compra completa entra en su objetivo, pero no se aprueba RNF-01 mientras fallen otros limites. No se han relajado umbrales ni se ha reducido la carga para ocultarlo.

| Criterio | Medido | Limite |
| --- | ---: | ---: |
| history.p95_ms | 507.20 | 500 |

Al reducir la espera se procesa mas trafico y se generan mas pedidos durante las mismas etapas. Los historiales crecen mas que en la linea base; no es una comparacion de bases con cardinalidad final identica. El perfil inicial, tiempos, objetivos y generador si permanecen iguales.

Si aun quedan limites incumplidos, usar el perfil SQL/HTTP para investigar materializacion, serializacion, espera de conexiones y dependencias bajo carga. Ya se reutilizan las conexiones HTTP; no atribuir automaticamente toda latencia a SQL ni ampliar recursos sin evidencia. Mantener objetivos y repetir la prueba tras cada correccion.

## Integridad

12322 solicitudes HTTP medidas; 0 errores inesperados. Compras totales contando calentamiento: 692. Integridad: APROBADA.

Pagos: {'paid': 692, 'other': 0, 'duplicate_orders': 0, 'published': 2076}. Pedidos: {'paid': 692, 'other': 0, 'unfinished_checkouts': 0}. Inventario: {'stock': 999308, 'consumed': 692, 'other': 0, 'processed_events': 692}.

## Entorno y recursos

Host Windows-11-10.0.26200-SP0; Docker 29.7.2, 8 CPU y 7.66 GiB. Contenedores adicionales activos: antes 20, despues 13. Generador y servicios comparten equipo. Versiones de dependencias iguales: True. Versiones medidas: {'python': '3.12.16', 'fastapi': '0.162.0', 'sqlalchemy': '2.1.6', 'uvicorn': '0.54.0', 'httpx': '0.28.1', 'pika': '1.4.4', 'psycopg2-binary': '2.9.13'}.

CPU 100 % representa aproximadamente un nucleo. Se muestrea cada cinco segundos mas el tiempo de docker stats; los maximos no necesariamente coinciden. No hay limites de recursos por servicio.

| Servicio | CPU media (%) | CPU maxima (%) | RAM maxima (MiB) | Muestras |
| --- | ---: | ---: | ---: | ---: |
| rabbitmq | 43.36 | 141.76 | 204.00 | 33 |
| order-service | 55.22 | 105.57 | 83.66 | 33 |
| product-service | 38.92 | 94.16 | 101.80 | 33 |
| payment-service | 32.05 | 67.98 | 101.80 | 33 |
| user-service | 12.19 | 45.82 | 89.62 | 33 |
| payment-db | 10.89 | 44.69 | 46.46 | 33 |
| order-db | 17.44 | 42.35 | 59.77 | 33 |
| product-db | 11.11 | 36.80 | 46.27 | 33 |
| user-db | 5.29 | 29.77 | 43.01 | 33 |
| cart-service | 12.74 | 29.72 | 80.30 | 33 |
| api-gateway | 5.88 | 22.46 | 9.67 | 33 |
| redis | 2.65 | 10.96 | 10.68 | 33 |
| notification-service | 0.87 | 3.45 | 39.89 | 33 |

## Alcance y reproducibilidad

Carga cerrada a 1/5/10/20 usuarios, 60 segundos programados por etapa y 15 segundos de calentamiento excluido. La duracion real incluye ciclos en curso. Preparacion, registro y login fuera de la medida. Catalogo de 100 productos; paginas de 20; compra de un producto compartido con stock suficiente; historiales pequenos que crecen por etapa. Los sondeos quedan fuera del throughput util; la compra termina al observar PAID. Integridad de inventario y eventos se verifica despues de drenar pendientes.

No demuestra sostenibilidad durante horas, saturacion, tasas abiertas de llegada, grandes bases, replicas, otros hosts ni SLA de produccion. Hay diferencias de carga externa no controladas entre ejecuciones. Las dependencias no estan fijadas, aunque se registran y comparan versiones. La instalacion habitual no se modifica por el benchmark y el proyecto aislado se elimina al terminar.

```powershell
python -X utf8 tests/performance_metrics_test.py
python -X utf8 tests/performance_load.py
python -X utf8 tests/performance_report.py
```

[Resultado](resultado.json), [CSV](metricas.csv), [muestras](resultado-muestras.jsonl), [recursos](resultado-recursos.json), [recursos resumidos](recursos-resumen.json), [comparacion JSON](comparacion-outbox.json), [hashes](evidencias.json), [linea base completa](../baseline-1a8d097/informe.md). Log local: ejecucion.log. La etiqueta v0.1.0-rc.1 permanece intacta.

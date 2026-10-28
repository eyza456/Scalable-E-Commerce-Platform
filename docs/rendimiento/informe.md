# Rendimiento tras optimizar Outbox

**Resultado: OBJETIVOS NO CUMPLIDOS.**

Se repitio la misma prueba: objetivos JSON, generador, calculo de metricas y preparacion de entorno con hashes identicos a la linea base. No se relajo ningun umbral. [Linea base preservada](baseline-9b6eeb3/README.md) y [objetivos](objetivos.md).

## Cambio y garantias

El worker drena inmediatamente cualquier lote sano, completo o parcial. Cuando la cola esta vacia espera un segundo; si falla una entrega o hay excepcion de DB mantiene el backoff de cinco segundos. Cada lote reutiliza una conexion/canal privados y declara una vez cada destino; conserva ACK por mensaje, mandatory, persistencia, IDs estables, SQL, skip_locked y entrega al menos una vez.

Las diez pruebas nuevas verifican drenaje de 120 entregas, backoff con fallos parciales/DB/broker, dos workers concurrentes, recuperacion tras fallo de commit, reutilizacion de canal, NACK, mensajes no enrutables y ausencia de conexiones al broker en vacio. Un fallo de commit despues del ACK puede reenviar el mismo ID; los consumidores siguen siendo idempotentes.

Se conserva tambien el [primer ensayo intermedio](iteracion-1-c81a190/README.md): solo drenar lotes completos dejo p95 en 10,203 s y no aprobo. La version final agrega menor espera en vacio y conexion por lote sin modificar el instrumento.

## Comparacion a 20 usuarios

| Metrica | Antes | Despues | Objetivo |
| --- | ---: | ---: | ---: |
| Compra p95 (s) | 10.839 | 8.205 | <=10 |
| Compra p99 (s) | 11.104 | 10.702 | <=15 |
| Solicitudes utiles/s | 41.30 | 58.47 | >=20 |
| Errores HTTP inesperados (%) | 0.00 | 0.00 | <1 |
| Compras medidas a 20 usuarios | 170 | 221 | >=100 |

Reduccion observada de p95: **24.30%**. Es una comparacion de dos ejecuciones locales, no una demostracion de causalidad exclusiva ni una estimacion de capacidad productiva.

## Etapas de la nueva ejecucion

| Usuarios | Segundos reales | HTTP | HTTP/s total | HTTP/s util | Errores (%) | Compra p95 (s) | Compra p99 (s) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 59.99 | 1058 | 17.64 | 15.40 | 0.00 | 1.288 | 1.353 |
| 5 | 61.11 | 4066 | 66.53 | 58.12 | 0.00 | 1.972 | 2.322 |
| 10 | 61.50 | 4922 | 80.03 | 69.14 | 0.00 | 3.219 | 3.821 |
| 20 | 61.71 | 4208 | 68.19 | 58.47 | 0.00 | 8.205 | 10.702 |

## Todos los objetivos de latencia a 20 usuarios

| Operacion | Muestras | p50 (ms) | p95 (ms) | p99 (ms) | Limite p95/p99 (ms) | Estado |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| catalog | 681 | 41.44 | 242.64 | 316.64 | 500/1000 | Cumple |
| product | 681 | 37.54 | 230.79 | 289.38 | 500/1000 | Cumple |
| profile | 681 | 21.00 | 75.98 | 119.02 | 500/1000 | Cumple |
| history | 681 | 268.99 | 804.31 | 1141.18 | 500/1000 | No cumple |
| cart_read | 221 | 19.72 | 172.84 | 209.31 | 500/1000 | Cumple |
| cart_add | 221 | 91.19 | 306.77 | 458.32 | 1500/3000 | Cumple |
| checkout | 221 | 1046.24 | 2894.15 | 3842.41 | 1500/3000 | No cumple |
| payment | 221 | 632.62 | 2488.61 | 3440.87 | 2000/5000 | No cumple |
| purchase_flow | 221 | 3401.40 | 8205.08 | 10702.00 | 10000/15000 | Cumple |

## Incumplimientos que siguen abiertos

La compra completa entra en su objetivo, pero no se aprueba RNF-01 mientras fallen otros limites. No se han relajado umbrales ni se ha reducido la carga para ocultarlo.

| Criterio | Medido | Limite |
| --- | ---: | ---: |
| history.p95_ms | 804.31 | 500 |
| history.p99_ms | 1141.18 | 1000 |
| checkout.p95_ms | 2894.15 | 1500 |
| checkout.p99_ms | 3842.41 | 3000 |
| payment.p95_ms | 2488.61 | 2000 |

Al reducir la espera se procesa mas trafico y se generan mas pedidos durante las mismas etapas. Los historiales crecen mas que en la linea base; no es una comparacion de bases con cardinalidad final identica. El perfil inicial, tiempos, objetivos y generador si permanecen iguales.

El siguiente trabajo es perfilar SQL y tiempos de espera del historial, y las llamadas HTTP/ocupacion de conexiones de checkout y pago bajo 20 usuarios. En el codigo actual se crean clientes HTTP sin reutilizacion por muchas llamadas entre servicios; es un candidato a investigar, no una causa demostrada por esta medicion. Medir trazas y planes antes de cambiar otros componentes. Mantener la mejora Outbox y repetir el mismo perfil despues de corregir esos puntos.

## Integridad

14254 solicitudes HTTP medidas; 0 errores inesperados. Compras totales contando calentamiento: 819. Integridad: APROBADA.

Pagos: {'paid': 819, 'other': 0, 'duplicate_orders': 0, 'published': 2457}. Pedidos: {'paid': 819, 'other': 0, 'unfinished_checkouts': 0}. Inventario: {'stock': 999181, 'consumed': 819, 'other': 0, 'processed_events': 819}.

## Entorno y recursos

Host Windows-11-10.0.26200-SP0; Docker 29.7.2, 8 CPU y 7.66 GiB. Contenedores adicionales activos: antes 20, despues 20. Generador y servicios comparten equipo. Versiones de dependencias iguales: True. Versiones medidas: {'python': '3.12.16', 'fastapi': '0.162.0', 'sqlalchemy': '2.1.6', 'uvicorn': '0.54.0', 'httpx': '0.28.1', 'pika': '1.4.4', 'psycopg2-binary': '2.9.13'}.

CPU 100 % representa aproximadamente un nucleo. Se muestrea cada cinco segundos mas el tiempo de docker stats; los maximos no necesariamente coinciden. No hay limites de recursos por servicio.

| Servicio | CPU media (%) | CPU maxima (%) | RAM maxima (MiB) | Muestras |
| --- | ---: | ---: | ---: | ---: |
| order-service | 76.30 | 157.84 | 144.30 | 34 |
| rabbitmq | 50.91 | 146.27 | 209.10 | 34 |
| payment-service | 36.32 | 88.34 | 181.40 | 34 |
| product-service | 35.19 | 71.97 | 102.80 | 34 |
| order-db | 14.29 | 50.49 | 63.39 | 34 |
| cart-service | 17.16 | 41.95 | 130.80 | 34 |
| user-service | 12.56 | 39.38 | 89.67 | 34 |
| payment-db | 6.81 | 24.59 | 48.43 | 34 |
| product-db | 8.57 | 21.44 | 44.89 | 34 |
| api-gateway | 5.27 | 17.55 | 12.96 | 34 |
| user-db | 3.47 | 15.82 | 41.69 | 34 |
| redis | 2.71 | 10.61 | 16.21 | 34 |
| notification-service | 0.59 | 1.65 | 40.06 | 34 |

## Alcance y reproducibilidad

Carga cerrada a 1/5/10/20 usuarios, 60 segundos programados por etapa y 15 segundos de calentamiento excluido. La duracion real incluye ciclos en curso. Preparacion, registro y login fuera de la medida. Catalogo de 100 productos; paginas de 20; compra de un producto compartido con stock suficiente; historiales pequenos que crecen por etapa. Los sondeos quedan fuera del throughput util; la compra termina al observar PAID. Integridad de inventario y eventos se verifica despues de drenar pendientes.

No demuestra sostenibilidad durante horas, saturacion, tasas abiertas de llegada, grandes bases, replicas, otros hosts ni SLA de produccion. Hay diferencias de carga externa no controladas entre ejecuciones. Las dependencias no estan fijadas, aunque se registran y comparan versiones. La instalacion habitual no se modifica por el benchmark y el proyecto aislado se elimina al terminar.

```powershell
python -X utf8 tests/performance_metrics_test.py
python -X utf8 tests/performance_load.py
python -X utf8 tests/performance_report.py
```

[Resultado](resultado.json), [CSV](metricas.csv), [muestras](resultado-muestras.jsonl), [recursos](resultado-recursos.json), [recursos resumidos](recursos-resumen.json), [comparacion JSON](comparacion-outbox.json), [hashes](evidencias.json), [linea base completa](baseline-9b6eeb3/informe.md). Log local: ejecucion.log. La etiqueta v0.1.0-rc.1 permanece intacta.

# Rendimiento medido - 28 de octubre de 2026

**Resultado: objetivos parcialmente cumplidos.** RNF-01 pasa de Pendiente a Parcial: ahora hay objetivos y evidencia de carga, pero la compra completa excede el limite p95 predefinido. No se ajustaron los objetivos para aprobar.

## Objetivos y entorno

[Perfil y criterios definidos antes de medir](objetivos.md). Limites: lecturas p95 500 ms/p99 1.000 ms; escrituras 1.500/3.000 ms; pago 2.000/5.000 ms; compra completa 10.000/15.000 ms; errores <1 %; >=20 solicitudes utiles/s y >=100 muestras por operacion en la etapa de 20 usuarios.

Host: Windows-11-10.0.26200-SP0; Docker Desktop 29.7.2, 8 CPU y 7.66 GiB. Habia 20 contenedores adicionales activos. Generador en el mismo equipo; no es servidor dedicado. Una instancia de cada servicio, sin replicas. Datos iniciales: 20 usuarios, 100 productos y stock suficiente; pagina de catalogo/historial de 20.

Imagenes nuevas con Python 3.12.16, FastAPI 0.162.0, SQLAlchemy 2.1.6, Uvicorn 0.54.0, HTTPX 0.28.1 y Pika 1.4.4; las dependencias aun no estan fijadas por version.

Carga cerrada con conexiones persistentes; preparacion y calentamiento excluidos. Por cada compra se hacen 12 consultas de navegacion; los sondeos se cuentan aparte. La duracion real incluye ciclos iniciados que terminan despues de los 60 s programados. Las etapas se ejecutan en secuencia y el historial crece durante la prueba.

## Escalones de carga

| Usuarios | Duracion real (s) | HTTP | HTTP/s total | HTTP/s util, sin sondeos | Errores | Compras medidas | Compra p95 (s) | Compra p99 (s) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 60.12 | 316 | 5.26 | 3.19 | 0.00% | 12 | 5.380 | 5.380 |
| 5 | 63.25 | 1591 | 25.15 | 15.18 | 0.00% | 60 | 5.384 | 5.408 |
| 10 | 62.98 | 2935 | 46.60 | 27.95 | 0.00% | 110 | 6.889 | 7.403 |
| 20 | 65.86 | 4865 | 73.87 | 41.30 | 0.00% | 170 | 10.839 | 11.104 |

## Latencia con 20 usuarios

| Operacion | Muestras | p50 (ms) | p95 (ms) | p99 (ms) | Limites p95/p99 (ms) | Estado |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| catalog | 510 | 13.78 | 87.04 | 104.51 | 500/1000 | Cumple |
| product | 510 | 12.31 | 80.84 | 96.31 | 500/1000 | Cumple |
| profile | 510 | 7.86 | 29.96 | 59.04 | 500/1000 | Cumple |
| history | 510 | 66.65 | 164.88 | 196.36 | 500/1000 | Cumple |
| cart_read | 170 | 7.25 | 67.28 | 79.77 | 500/1000 | Cumple |
| cart_add | 170 | 38.94 | 104.64 | 150.86 | 1500/3000 | Cumple |
| checkout | 170 | 360.61 | 720.91 | 868.71 | 1500/3000 | Cumple |
| payment | 170 | 214.39 | 504.07 | 664.71 | 2000/5000 | Cumple |
| purchase_flow | 170 | 5957.89 | 10839.01 | 11103.89 | 10000/15000 | No cumple |

Se midieron **9707 solicitudes HTTP** sin errores inesperados. A 20 usuarios se sostuvieron **41.30 solicitudes utiles/s**, por encima del minimo 20. Cada operacion critica tiene al menos 170 muestras. El unico criterio incumplido es purchase_flow.p95: **10,839 s frente a 10 s**, un exceso de 0,839 s (8,39 %).

El tiempo de compra incluye crear carrito/pedido, pagar y esperar mediante sondeos hasta observar PAID. No es solamente la latencia de POST /payments. Los sondeos a intervalos de 500 ms anaden resolucion temporal a la observacion.

## Integridad bajo carga

Se verificaron por SQL **372 compras** contando el calentamiento: 372 pedidos PAID, 372 pagos PAID, 372 reservas CONSUMED, 372 eventos de inventario procesados y 1.116 entregas Outbox PUBLISHED. Stock inicial 1.000.000 y final 999.628. Sin pagos duplicados por pedido, checkouts inconclusos, pagos rechazados inesperados, eventos pendientes ni errores de los usuarios virtuales. Las 352 compras de las etapas medidas excluyen las 20 del calentamiento.

## Recursos observados

docker stats se muestreo aproximadamente cada cinco segundos mas el tiempo de la consulta. CPU 100 % equivale aproximadamente a un nucleo, no al total de ocho CPU; los picos de distintos servicios no necesariamente coinciden. Los limites de memoria no estan configurados por servicio.

| Contenedor | CPU media (%) | CPU maxima (%) | RAM maxima (MiB) | Muestras |
| --- | ---: | ---: | ---: | ---: |
| order-service | 28.84 | 144.26 | 142.70 | 36 |
| rabbitmq | 28.41 | 117.58 | 199.20 | 36 |
| payment-service | 10.50 | 50.02 | 161.90 | 36 |
| product-service | 10.05 | 47.67 | 100.40 | 36 |
| cart-service | 6.28 | 36.08 | 114.70 | 36 |
| order-db | 5.19 | 33.35 | 52.18 | 36 |
| user-service | 3.83 | 17.73 | 89.91 | 36 |
| product-db | 2.65 | 16.85 | 45.95 | 36 |
| payment-db | 2.30 | 14.26 | 44.32 | 36 |
| api-gateway | 2.38 | 11.25 | 9.40 | 36 |
| user-db | 1.69 | 9.45 | 45.61 | 36 |
| redis | 1.17 | 5.42 | 10.12 | 36 |
| notification-service | 0.23 | 1.09 | 37.88 | 36 |

## Interpretacion y siguiente cambio recomendado

Las APIs responden dentro de los limites; el mayor retraso aparece al esperar que el evento cambie el pedido a PAID. El principal candidato es el despacho Outbox: dispatch_pending procesa hasta 50 entregas y run_outbox espera cinco segundos despues de cada lote. Cada pago genera tres entregas. Una rafaga de 20 pagos genera 60 entregas y puede necesitar dos rondas de despacho. Este mecanismo es coherente con el salto a aproximadamente 11 s de compra en las colas altas, pero no se ha hecho una comparacion A/B que demuestre causalidad exclusiva.

Siguiente trabajo: drenar lotes consecutivos cuando haya pendientes, conservando skip_locked, transaccion, reintentos y entrega al menos una vez; esperar solo cuando no haya trabajo o se aplique backoff. Repetir exactamente este perfil y mantener los objetivos. Si aun falla, instrumentar created_at/published_at/consumo y trazar el flujo antes de cambiar otros componentes. No se modifico el codigo funcional en esta medicion.

## Limites de la evidencia

Es una medicion local de cuatro etapas de un minuto, con historiales pequenos y un solo producto comprado. No demuestra carga sostenida de horas, picos abiertos de llegadas, catalogos grandes, escala horizontal, otros hosts o capacidad productiva. Un generador cerrado reduce su ritmo cuando aumenta la latencia; no permite inferir la cola de llegadas a una tasa externa fija. Los percentiles p99 son estimaciones con 170 compras a carga maxima. La contencion con otros contenedores y el generador local influyen en los resultados.

## Reproducir y revisar

```powershell
python -X utf8 tests/performance_metrics_test.py
python -X utf8 tests/performance_load.py --smoke
python -X utf8 tests/performance_load.py
```

La prueba breve paso y se aprobaron seis tests del calculo/evaluacion de metricas. La ejecucion completa termino normalmente, guardo evidencias y elimino exclusivamente su proyecto Docker; el instrumento senala no aceptacion porque hay un objetivo incumplido. La instalacion habitual continuo activa. La etiqueta v0.1.0-rc.1 no se mueve.

[Resultado estructurado](resultado.json), [CSV por operacion/etapa](metricas.csv), [muestras crudas](resultado-muestras.jsonl), [recursos crudos](resultado-recursos.json), [recursos resumidos](recursos-resumen.json), [validacion breve](smoke.json), [huellas de evidencia](evidencias.json). Log local: ejecucion.log.

Las huellas de evidencias normalizan CRLF a LF para permitir verificacion entre checkouts Windows/Linux. source_commit identifica la base de la aplicacion medida; los hashes identifican ademas las herramientas nuevas de carga. La matriz distingue Parcial (medido con objetivo incumplido) de Pendiente (sin evidencia).

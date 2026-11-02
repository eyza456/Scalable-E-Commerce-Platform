# Perfilado de historial, checkout y pago

Diagnostico en proyectos Docker separados, con 20 usuarios, 100 productos, cinco segundos de calentamiento y 30 segundos de carga. El mismo instrumento fue inyectado en las copias de Order, Payment, Cart y Product; no forma parte de las aplicaciones desplegadas. Los datos agregados incluyen calentamiento y no se usan para aprobar RNF-01. La aceptacion se obtiene del [benchmark original sin instrumentacion](../rendimiento/informe.md).

## Metodo y alcance de los contadores

- total_ms: peticion ASGI completa, con dependencias y limpieza de sesion.
- db_connect_ms: adquisicion del engine, incluyendo espera de pool y nueva conexion si corresponde; no separa ambos costes.
- db_execute_ms: cursor SQL, incluyendo bloqueos y espera del driver; no incluye toda la materializacion ORM.
- orm_all_ms: Query.all completo, incluyendo SQL, materializacion y carga de relaciones. Aplica al historial; checkout/pago usan otros metodos ORM.
- db_held_ms: tiempo de prestamo de conexiones; puede incluir llamadas HTTP y serializacion mientras la sesion sigue abierta.
- http_client_init_ms: construccion de Client HTTPX por llamada. En la mejora el transporte/TLS se construye una vez y se amortiza; ese primer coste sigue dentro de total_ms.
- http_send_ms: envio HTTP, espera de transporte/red y servicio remoto, incluida lectura de la respuesta HTTPX; urllib mide hasta las cabeceras.
- serialize_ms: validacion/conversion de respuesta de FastAPI, incluyendo esperas de programacion; no representa exclusivamente CPU ni todo el renderizado JSON. En el historial optimizado la validacion y el renderizado se hacen explicitamente en el worker; serialize_ms de FastAPI puede ser cero sin que se haya omitido validacion.

Los contadores se solapan: no sumar columnas ni percentiles. Parte del tiempo restante incluye cola del threadpool, dependencias, ORM no cubierto y programacion del event loop. Las trazas enlazan llamadas mediante un ID sintetico; no guardan tokens, cuerpos ni parametros SQL. Solo se almacenan tabla y duracion de cada sentencia.

## Comparacion diagnostica (p95 en ms)

| Ruta | Contador | Antes | Despues |
| --- | --- | ---: | ---: |
| GET /orders | total_ms | 635.27 | 361.84 |
| GET /orders | db_connect_ms | 57.67 | 37.90 |
| GET /orders | db_execute_ms | 71.80 | 33.92 |
| GET /orders | orm_all_ms | 121.95 | 61.84 |
| GET /orders | db_held_ms | 317.35 | 69.02 |
| GET /orders | http_client_init_ms | 0.00 | 0.00 |
| GET /orders | http_send_ms | 0.00 | 0.00 |
| GET /orders | serialize_ms | 124.68 | 0.00 |
| POST /orders | total_ms | 1618.35 | 1199.20 |
| POST /orders | db_connect_ms | 102.81 | 80.01 |
| POST /orders | db_execute_ms | 346.56 | 276.62 |
| POST /orders | db_held_ms | 1314.93 | 927.90 |
| POST /orders | http_client_init_ms | 316.35 | 1.87 |
| POST /orders | http_send_ms | 444.21 | 580.97 |
| POST /orders | serialize_ms | 154.91 | 91.96 |
| POST /payments | total_ms | 1457.78 | 1022.42 |
| POST /payments | db_connect_ms | 75.30 | 22.50 |
| POST /payments | db_execute_ms | 204.39 | 141.86 |
| POST /payments | db_held_ms | 956.79 | 669.26 |
| POST /payments | http_client_init_ms | 150.82 | 1.32 |
| POST /payments | http_send_ms | 959.18 | 823.20 |
| POST /payments | serialize_ms | 35.21 | 16.05 |

## Planes SQL en reposo

Despues de drenar el trabajo se ejecuta EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) sobre historial del usuario con mas pedidos, historial filtrado PAID y seleccion de items de los ultimos 20 pedidos. No se ejecuta sobre datos reales del usuario. Son planes en reposo y cache caliente, no evidencia de ausencia de contencion durante carga.

| Consulta | Ejecucion antes (ms) | Ejecucion despues (ms) | Plan antes/despues |
| --- | ---: | ---: | --- |
| history | 0.202 | 0.140 | Limit / Limit |
| history_paid | 0.083 | 0.065 | Limit / Limit |
| order_items | 0.217 | 0.155 | Hash Join / Hash Join |

## Decision y resultado

Los planes del conjunto pequeno son baratos, mientras la construccion repetida de clientes HTTP tiene coste medible y mantiene conexiones SQL ocupadas durante el checkout. Se reutiliza el transporte HTTP en tres servicios; cada llamada conserva un cliente efimero para evitar mezclar cookies o encabezados de autenticacion. En el historial se valida el modelo publico en el worker, se copia su representacion JSON y se libera la conexion de lectura antes del renderizado; asi se evita otra ronda de validacion ORM en el event loop/threadpool. El esquema, filtros por usuario y orden/paginacion se mantienen. No se agregaron indices ni se ampliaron pools SQL para ocultar esperas. No se introdujeron reintentos de POST, cache de precios/stock ni omision de validaciones.

El contador de construccion HTTP baja claramente, pero este diagnostico no demuestra por si solo una mejora global: tambien hay espera/ORM/serializacion y variacion de carga del equipo. Las latencias totales no se aprobaron a partir de esta corrida. El resultado vinculante del perfil local esta en el benchmark completo sin hooks.

Registros capturados: antes 3537, despues 4295. Compras integras: antes 132, despues 156. El volumen final no es identico porque el generador es cerrado y el numero de ciclos depende de las respuestas. No son mediciones de saturacion ni un SLA productivo.

Se preserva un [fallo de arranque aislado](arranque-fallido.json): RabbitMQ no pudo leer su cookie antes de iniciar las aplicaciones. Se elimino ese proyecto y el siguiente arranque limpio completo el perfil. No se utilizo ese intento como muestra de rendimiento.

## Reproducir

```powershell
python -X utf8 tests/profile_api.py --label antes
# Aplicar el cambio que se desea comparar
python -X utf8 tests/profile_api.py --label despues
python -X utf8 tests/profile_report.py
```

Para reconstruir el antes exacto usar el codigo del source_commit registrado en antes.json; no volver a generar antes sobre el codigo optimizado. El instrumento se conserva en tests/profile_instrument.py y ambos resultados incluyen su hash. Los proyectos y volumenes temporales se eliminan. Logs locales antes.log/despues.log excluidos de Git.

[Resumen JSON](resumen.json), [datos antes](antes-requests.jsonl), [datos despues](despues-requests.jsonl), [planes antes](antes-planes.json), [planes despues](despues-planes.json), [metadatos antes](antes.json), [metadatos despues](despues.json).

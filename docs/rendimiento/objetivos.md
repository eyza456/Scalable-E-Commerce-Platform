# Objetivos iniciales de rendimiento - perfil local-mvp-20vu-v1

Definidos antes de la primera ejecucion de aceptacion. Son criterios de ingenieria para el backend MVP en Docker Desktop local, no un SLA de produccion ni objetivos negociados con negocio. Se registran en tests/performance_goals.json y su hash se guarda en cada resultado. No se modifican los umbrales para aprobar un resultado observado.

## Carga y alcance

- 20 usuarios concurrentes autenticados, cada uno con su carrito; todos compran el mismo producto para ejercer contencion de inventario.
- Catalogo inicial de 100 productos, pagina de 20, stock suficiente (1.000.000 por producto), precio 10. Un usuario virtual realiza 12 consultas de navegacion (catalogo, detalle, perfil e historial) seguidas de una compra (agregar al carrito, consultar version, checkout y pago).
- Carga cerrada: cada usuario espera su respuesta y termina la confirmacion antes de iniciar otro ciclo. No hay tasa fija de llegadas ni prueba de saturacion. No modela pausas humanas.
- Conexion HTTP persistente por usuario al gateway; un solo cliente secuencial por usuario. Los sondeos de pedido/checkout se miden aparte y no cuentan para el minimo de solicitudes utiles.
- Preparacion de usuarios, registro, login y siembra SQL fuera de la medicion. No se afirma rendimiento del registro/bcrypt, catalogos grandes ni millones de pedidos historicos.
- Calentamiento de 15 segundos a cinco usuarios, excluido de percentiles. Etapas de 60 segundos a 1, 5, 10 y 20 usuarios; se deja terminar cada ciclo ya iniciado. El informe muestra duracion programada y real, incluidos finales pendientes, y usa la duracion real para calcular throughput.

## Criterios de aceptacion a 20 usuarios

| Operacion | p95 maximo | p99 maximo |
| --- | ---: | ---: |
| Catalogo, producto, perfil, historial y consulta de carrito | 500 ms | 1.000 ms |
| Agregar al carrito y crear pedido | 1.500 ms | 3.000 ms |
| Solicitud de pago | 2.000 ms | 5.000 ms |
| Compra hasta pedido PAID, incluyendo espera de eventos y sondeo | 10.000 ms | 15.000 ms |

Ademas:

- Menos del 1 % de errores HTTP/transportes inesperados. Se conservan latencias y codigos de solicitudes fallidas; no se esconden de los percentiles.
- Al menos 20 solicitudes utiles por segundo en la etapa de 20 usuarios, excluyendo sondeos y temporizadores del flujo completo.
- Al menos 100 muestras por operacion y flujo para poder aceptar. p99 con este volumen sigue siendo una estimacion local; no es un estudio estadistico de colas extremas.
- Cero violaciones de integridad: sin pedidos/pagos duplicados, total correcto, permisos privados conservados, exactamente un descuento y reserva consumida por compra, tres eventos publicados por pago y ausencia de pendientes al terminar.

Un percentil rapido no compensa un error de integridad. Una muestra insuficiente no se considera aprobacion. Las etapas inferiores permiten comparar degradacion; la aceptacion de este perfil corresponde a 20 usuarios.

## Entorno y recursos

Se crea otro proyecto Compose, con credenciales y cuatro volumenes nuevos, construido desde fuentes versionadas. Se aplican migraciones y se comprueban tablas vacias antes de sembrar datos. La instalacion habitual permanece activa, por lo que comparte recursos del equipo; no es un servidor dedicado.

El informe captura CPU y RAM disponibles para Docker, sistema host, versiones de dependencias y contenedores coexistentes. docker stats se muestrea cada cinco segundos aproximadamente y se guarda por contenedor (CPU, memoria, red, E/S y PIDs). El muestreo es orientativo y tiene coste en el mismo equipo que genera la carga.

## Reproducir

Desde la raiz, con Docker Desktop y Python 3.11+:

```powershell
python -X utf8 tests/performance_metrics_test.py
python -X utf8 tests/performance_load.py --smoke
python -X utf8 tests/performance_load.py
```

La ejecucion breve valida el instrumento y la integridad; nunca aprueba los objetivos de carga. La completa dura varios minutos mas construccion/preparacion y devuelve codigo 0 si se cumplen todos los objetivos, 2 si se midio pero no se cumplen, y otro codigo ante fallo de ejecucion. El proyecto de prueba se elimina incluso si no cumple objetivos.

Archivos: resultado.json (entorno, metas, etapas e invariantes), resultado-muestras.jsonl (latencias sin tokens), resultado-recursos.json (muestreo de contenedores). El log local ejecucion.log no se versiona. La suite funcional y el benchmark permanecen separados para no convertir cada prueba de regresion en una prueba de carga.

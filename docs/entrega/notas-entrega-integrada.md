# Notas de cierre integrado - 1 de noviembre de 2026

Documentacion final del candidato local de backend + frontend. Codigo funcional
actual `d563b2c`: separación completa de checkout, contratos y migraciones, además de operaciones de pedidos/carrito, pagos,
usuarios y catalogo, repositorios, adaptadores de checkout e importacion ASGI sin efectos. Se conservan los contratos
publicos y los objetivos de rendimiento. La etiqueta historica `v0.1.0-rc.1`
se conserva sin moverla.

## Incorporado desde la RC original

- Frontend Nexo basado en Stitch, Nginx y acceso mediante API Gateway.
- Registro/login y perfil editable con token renovado; catalogo y filtros reales.
- Carrito, checkout por version y recuperacion sin POST automaticos duplicados.
- Pago simulado, motivos/fecha final y consulta privada del ultimo intento.
- Historial, detalle/pago de pedidos anteriores y cancelacion confirmada.
- Mejoras de foco, dialogo, semantica y adaptacion de las vistas revisadas.
- Instalacion nueva incluyendo frontend, aislada de los datos locales.
- Matriz de 78 requisitos ampliada con cobertura visual, sin aumentar el conteo.
- Preparación futura: Kustomize base/dev, TLS local validado con Nginx, runner de fallo de réplica y helpers de instalación PowerShell/POSIX.

## Evidencia utilizada

| Evidencia | Resultado y alcance |
| --- | --- |
| Backend completo, suite-pagos-modular.log | Reejecutado sobre el refactor: 164 unittest, seis importaciones ASGI sin efectos y HTTP/migracion/TTL-DLQ/gateway/demo; [resultado](../auditoria/resultado-suite.json) |
| Cinco regresiones frontend | 56 escenarios aprobados; se conservan las fechas registradas, no se afirman repetidos por editar documentos |
| Recorrido cliente completo | Nueve etapas; 14 estados axe sin incidencias/incompletos; teclado y doce comprobaciones de ancho; [guion](../frontend/demostracion-visual.md) |
| Instalacion completa | 14 contenedores nuevos; migraciones, compra, eventos, reinicio/persistencia y navegador; [informe](../frontend/instalacion-desde-cero.md) |
| Rendimiento backend/gateway | Referencia historica de una instancia conservada; nueva carga multinstancia con los mismos objetivos en [escalabilidad](../escalabilidad/README.md); no se mide rendimiento web |

Los JSON distinguen fecha de ejecucion y revision. Los 164 unittest no incluyen
los 56 escenarios del navegador. Tests dirigidos de consulta de pagos, perfil y
metricas tienen evidencias separadas; no se suman como otra suite total ejecutada.

La instalación limpia se reejecutó sobre `d563b2c` y quedó aprobada; las pruebas multinstancia históricas se conservan con sus hashes de origen;
los hashes del informe corresponden a esa revisión.

## Limites explicitos

**74 cumplidos, 4 parciales, 0 pendientes.** La cobertura GUI no convierte toda
capacidad de API en pantalla: productos/categorias, roles, estados administrativos
y vaciado completo del carrito carecen de controles visuales dedicados.

No hay pago bancario, envios, promociones, recuperacion de contraseña o verificacion
del correo nuevo. Acceso local HTTP y sesion en memoria. Se acreditan replicas
locales; quedan sin verificar alta disponibilidad, SLA productivo, otro host/OS,
lector de pantalla y toda WCAG.
Las aprobaciones simuladas si modifican el inventario local.

## Integridad y publicacion

[Manifiesto](manifiesto-entrega.json): hashes de fuentes, configuracion, documentos
y evidencias. Excluye `.env`, tokens, herramientas y dependencias instaladas.
Se entrega como commit local, sin push, publicacion web ni nueva etiqueta.

## Ampliacion posterior: multinstancia local

RNF-05/06 cerrados con [configuracion y pruebas](../escalabilidad/README.md): dos replicas por servicio, escalado independiente de los seis y carga original aprobada. La RC historica se conserva; no se declara alta disponibilidad ni balanceo uniforme.

La preparación futura no cambia los estados formales: RNF-07 tiene manifiestos renderizables pero falta aplicar en cluster; RNF-15 tiene HTTPS local pero falta CA/rotación; RF-49 tiene runner de failover pero falta observación en dos réplicas vivas; RNF-27 tiene scripts portables pero falta ejecutar en Linux/macOS.

La etapa inicial multinstancia conservo las pruebas anteriores. Tras este refactor
se repiten la suite backend (164), instalacion con recorrido UI y pruebas/carga
multinstancia. Los 56 escenarios GUI previos conservan su fecha; no se suman al
recorrido UI nuevo ni se presentan como reejecutados.

## Modularidad: cierre de RNF-08/RNF-21

[Cambios y contratos](../modularidad.md) y [separacion de pagos](../modularidad-pagos.md).
Checkout y recuperadores comparten repositorio, cancelaciones y eventos usan
contratos tipados, y User/Order/Payment aplican migraciones versionadas idempotentes.

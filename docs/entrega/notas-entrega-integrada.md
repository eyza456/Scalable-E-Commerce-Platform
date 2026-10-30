# Notas de cierre integrado - 29 de octubre de 2026

Documentacion final del candidato local de backend + frontend. Codigo funcional
actual `1cfacff`: primera separacion de operaciones de pedidos/carrito, segunda
separacion de pagos, repositorio, adaptadores de checkout e importacion ASGI sin efectos. Se conservan los contratos
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

## Evidencia utilizada

| Evidencia | Resultado y alcance |
| --- | --- |
| Backend completo, suite-pagos-modular.log | Reejecutado sobre el refactor: 161 unittest, seis importaciones ASGI sin efectos y HTTP/migracion/TTL-DLQ/gateway/demo; [resultado](../auditoria/resultado-suite.json) |
| Cinco regresiones frontend | 56 escenarios aprobados; se conservan las fechas registradas, no se afirman repetidos por editar documentos |
| Recorrido cliente completo | Nueve etapas; 14 estados axe sin incidencias/incompletos; teclado y doce comprobaciones de ancho; [guion](../frontend/demostracion-visual.md) |
| Instalacion completa | 14 contenedores nuevos; migraciones, compra, eventos, reinicio/persistencia y navegador; [informe](../frontend/instalacion-desde-cero.md) |
| Rendimiento backend/gateway | Referencia historica de una instancia conservada; nueva carga multinstancia con los mismos objetivos en [escalabilidad](../escalabilidad/README.md); no se mide rendimiento web |

Los JSON distinguen fecha de ejecucion y revision. Los 161 unittest no incluyen
los 56 escenarios del navegador. Tests dirigidos de consulta de pagos, perfil y
metricas tienen evidencias separadas; no se suman como otra suite total ejecutada.

La instalacion se probo con los hashes que constan en su informe; corresponden al
snapshot `1cfacff`. Los enlaces y resumenes finales se actualizan despues sin
cambiar pasos de arranque ni fuentes funcionales. No se reescriben hashes de
instalacion para aparentar una version distinta.

## Limites explicitos

**72 cumplidos, 6 parciales, 0 pendientes.** La cobertura GUI no convierte toda
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

La etapa inicial multinstancia conservo las pruebas anteriores. Tras este refactor
se repiten la suite backend (161), instalacion con recorrido UI y pruebas/carga
multinstancia. Los 56 escenarios GUI previos conservan su fecha; no se suman al
recorrido UI nuevo ni se presentan como reejecutados.

## Modularidad: avance parcial

[Cambios y siguientes extracciones](../modularidad.md) y [separacion de pagos](../modularidad-pagos.md). RNF-08/21 siguen parciales:
hay otros routers y recuperadores por separar, contratos por extender y bootstrap
por sustituir con migraciones versionadas en tres servicios.

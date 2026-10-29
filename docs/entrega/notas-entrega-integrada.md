# Notas de cierre integrado - 29 de octubre de 2026

Documentacion final del candidato local de backend + frontend. Codigo funcional
base `7338855`; este cierre no cambia aplicaciones, contratos ni objetivos de
rendimiento. La etiqueta historica `v0.1.0-rc.1` se conserva sin moverla.

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
| Backend completo, suite-entrega-frontend.log | Reejecutado para este cierre: 153 unittest, 0 fallos y HTTP/migracion/TTL-DLQ/gateway/demo; [resultado](../auditoria/resultado-suite.json) |
| Cinco regresiones frontend | 56 escenarios aprobados; se conservan las fechas registradas, no se afirman repetidos por editar documentos |
| Recorrido cliente completo | Nueve etapas; 14 estados axe sin incidencias/incompletos; teclado y doce comprobaciones de ancho; [guion](../frontend/demostracion-visual.md) |
| Instalacion completa | 14 contenedores nuevos; migraciones, compra, eventos, reinicio/persistencia y navegador; [informe](../frontend/instalacion-desde-cero.md) |
| Rendimiento backend/gateway | Medicion historica aceptada del perfil local de 20 usuarios; no se repite carga ni se mide rendimiento web |

Los JSON distinguen fecha de ejecucion y revision. Los 153 unittest no incluyen
los 56 escenarios del navegador. Tests dirigidos de consulta de pagos, perfil y
metricas tienen evidencias separadas; no se suman como otra suite total ejecutada.

La instalacion se probo con los hashes que constan en su informe; corresponden al
snapshot `7338855`. Los enlaces y resumenes finales se actualizan despues sin
cambiar pasos de arranque ni fuentes funcionales. No se reescriben hashes de
instalacion para aparentar una version distinta.

## Limites explicitos

**70 cumplidos, 8 parciales, 0 pendientes.** La cobertura GUI no convierte toda
capacidad de API en pantalla: productos/categorias, roles, estados administrativos
y vaciado completo del carrito carecen de controles visuales dedicados.

No hay pago bancario, envios, promociones, recuperacion de contraseña o verificacion
del correo nuevo. Acceso local HTTP y sesion en memoria. No se acreditan replicas,
alta disponibilidad, SLA productivo, otro host/OS, lector de pantalla ni toda WCAG.
Las aprobaciones simuladas si modifican el inventario local.

## Integridad y publicacion

[Manifiesto](manifiesto-entrega.json): hashes de fuentes, configuracion, documentos
y evidencias. Excluye `.env`, tokens, herramientas y dependencias instaladas.
Se entrega como commit local, sin push, publicacion web ni nueva etiqueta.

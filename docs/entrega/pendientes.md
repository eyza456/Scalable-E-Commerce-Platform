# Pendientes reales y prioridades

Revision: 29 de octubre de 2026. Matriz vigente: 72 cumplidos, 6 parciales y 0 pendientes de 78. No se incluyen como pendientes los seis defectos iniciales ya corregidos. RNF-01 ya cumple los objetivos del perfil local v1 tras el perfilado SQL/HTTP; no representa un SLA productivo. La RC etiquetada originalmente tenia 69/8/1; esta es la revision posterior. Los 12 criterios basicos de aceptacion de pp.22-23 tienen evidencia; eso no equivale a cumplir todos los RNF.

## Cierre del candidato integrado

| Elemento | Criterio de cierre | Estado |
| --- | --- | --- |
| Trazabilidad | Matriz de 78 requisitos con evidencia actual y auditoria anterior preservada | Cerrado |
| Funciones principales | Suite backend de 155 pruebas, 56 escenarios frontend registrados, recorrido visual y datos de prueba eliminados | Cerrado con evidencias y fechas separadas |
| Instalacion | Plantilla, migracion, esquema limpio y stack completo con frontend y navegador | Cerrado en Windows/Docker Linux; 14 contenedores nuevos |
| Version | RC historica v0.1.0-rc.1 preservada; revision integrada identificada por su commit y manifiesto | Cierre local, sin remoto ni nueva etiqueta |

No hay defectos funcionales conocidos abiertos de la auditoria anterior. Se entrega
un candidato de backend y frontend de cliente, no una declaracion de cumplimiento
integral ni un despliegue productivo.

## Cobertura visual que aun falta

Estas diferencias no cambian los 78 estados formales: las capacidades existen por API.

| Prioridad de ampliacion | Falta visual | Situacion de entrega |
| --- | --- | --- |
| Media | Boton dedicado de vaciado completo del carrito (RF-25) | Quitar items y checkout integrados; DELETE /api/cart disponible por API |
| Segun alcance administrativo | Alta/edicion/borrado de productos, categorias, stock, roles y transiciones de pedidos | APIs con permisos; sin consola administrativa GUI |
| Media | Revision con lector de pantalla, otro navegador y zoom real 200% | Axe en 14 estados y comprobaciones de teclado/reflow; no certificacion integral |

No hay recuperacion de contraseña, verificacion de correo o sesion persistente
en navegador; no se presentan como funcionalidades implementadas.

## Obligatorio antes de declarar cumplimiento integral o escalabilidad verificada

La [clasificacion de los ocho parciales](plan-cierre-parciales.md) detalla el
alcance y las pruebas de cierre. RNF-05/06 quedan cerrados en alcance local con el [perfil y las pruebas multinstancia](../escalabilidad/README.md). Restan tres parciales de calidad (RNF-08/21/27) y tres de preparacion futura. El siguiente bloque es modularidad/acoplamiento; portabilidad requiere otro host.

| Orden | Requisito | Falta y accion concreta | Evidencia para cerrar |
| --- | --- | --- | --- |
| Cerrado en alcance local | RNF-01, Cumplido | Referencia de una instancia: historial 286,88 ms, checkout 770,97 ms, pago 525,38 ms y compra 2,738 s en p95. El perfil multinstancia tambien aprueba los mismos 30 criterios | [Referencia](../rendimiento/informe.md), [perfil SQL/HTTP](../perfilado/informe.md) y [nueva carga](../escalabilidad/README.md). Ampliar volumen y duracion antes de inferir capacidad productiva |
| Cerrado en alcance local | RNF-05/06, Cumplido | Overlay aislado; dos instancias de los seis servicios, escalado independiente 2/3/1/2 y compra/cancelacion concurrentes | [Evidencias](../escalabilidad/README.md), incluido benchmark original aprobado; sin garantia productiva |
| 3 / media | RNF-27, Parcial | Ejecutar instalacion limpia en otro host compatible con Docker, Linux y/o macOS | Reporte del mismo fresh_install.py con host/version y resultado; contenedores Linux en Windows no son otro host |
| 4 / media | RNF-08/21, Parcial | Continuar extraccion en pagos/otros routers y contratos de cancelacion/eventos; versionar migraciones de usuarios/pedidos/pagos. Importacion sin efectos y separacion pedidos/carrito ya verificadas | [Primera etapa](../modularidad.md), regresion y contratos; falta completar el resto del backend |

Estos pendientes limitan la afirmacion de cumplimiento del PDF; no se han ocultado como capacidades productivas. Se entrega RC para revision y demostracion mientras siguen abiertos.

## Antes de exponer el sistema o alojar datos reales

| Prioridad | Limite actual | Siguiente trabajo |
| --- | --- | --- |
| Alta | Redis y RabbitMQ sin volumenes nombrados en Compose | Definir persistencia y recuperacion; probar recreacion con carritos, reservas y eventos pendientes. La prueba de reinicio no demuestra durabilidad al recrear |
| Alta | Acceso HTTP local y puertos directos publicados | Perfil de despliegue con HTTPS, certificados, puertos internos cerrados y gestion/rotacion de secretos |
| Alta | Recuperacion operativa y DLQ manuales | Procedimientos probados de respaldo/restauracion, alertas y reproceso idempotente |
| Media | /health de aplicaciones principalmente liveness | Readiness de DB/Redis/broker y monitoreo de colas/Outbox/recuperadores |
| Media | Administracion de usuarios/roles incompleta respecto al plano | Procedimiento de alta de administrador y luego endpoints administrativos con auditoria; la demo usa un token de fixture |
| Media | Dependencias Python sin versiones fijadas | Fijar un conjunto probado y ejecutar construccion/regresion en CI; el controlador PostgreSQL ya se selecciona explicitamente |

## Evolucion opcional para el MVP inicial

- RF-49: balanceo de carga real. Se tiene Nginx con DNS dinamico, recuperacion y replicas locales; falta medir y demostrar el reparto de solicitudes del gateway entre ellas.
- RNF-07: preparacion/despliegue Kubernetes. Sigue parcial; el PDF excluye la implementacion inicial completa de Kubernetes (p.8).
- RNF-15: HTTPS futuro. Sigue parcial; imprescindible antes de exposicion productiva.
- Pasarela real y reembolsos, Elasticsearch, inventario independiente, notificaciones externas, discovery especializado, logs centralizados, Prometheus/Grafana, CI/CD y autoscaling (pp.8,22,36-37).

Son opciones de evolucion del alcance inicial; no se consideran implementadas por existir carpetas de infraestructura o dependencias. El orden recomendado tras revisar esta RC es reducir acoplamiento, completar modularidad y verificar portabilidad, y ampliar duracion/volumen de las pruebas de rendimiento, antes de anunciar escalabilidad o disponibilidad productiva.

# Pendientes reales y prioridades

Revision: 1 de noviembre de 2026. Matriz vigente: 74 cumplidos, 4 parciales y 0 pendientes de 78. No se incluyen como pendientes los seis defectos iniciales ya corregidos. RNF-01 tiene objetivos medidos en el perfil local, pero no representa un SLA productivo. La preparación futura de Kubernetes, TLS, fallo de réplicas y portabilidad está documentada en [preparacion-futura.md](../preparacion-futura.md).

## Cierre del candidato integrado

| Elemento | Criterio de cierre | Estado |
| --- | --- | --- |
| Trazabilidad | Matriz de 78 requisitos con evidencia actual y auditoria anterior preservada | Cerrado |
| Funciones principales | Suite backend de 161 pruebas, 56 escenarios frontend registrados, recorrido visual y datos de prueba eliminados | Cerrado con evidencias y fechas separadas |
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
| 3 / media | RNF-27, Parcial | Ejecutar instalación limpia en un host Linux y otro macOS; ya existen helpers PowerShell/POSIX | [Preparación futura](../preparacion-futura.md) y `tests/frontend_fresh_install.py` |
| 4 / media | RNF-07/15/49, Parciales | Aplicar Kubernetes en un cluster, usar certificados confiables y observar fallo/reparto de réplicas en un entorno real | [Preparación futura](../preparacion-futura.md); los manifests y runners locales ya están preparados |

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

- RF-49: balanceo de carga real. Se tiene Nginx con DNS dinamico, recuperacion, runner de fallo de replica y replicas locales; falta una observacion productiva del reparto.
- RNF-07: manifests Kustomize y validacion offline preparados; falta aplicar y operar un cluster real.
- RNF-15: configuración TLS local preparada; falta CA confiable, rotación y validación productiva.
- Pasarela real y reembolsos, Elasticsearch, inventario independiente, notificaciones externas, discovery especializado, logs centralizados, Prometheus/Grafana, CI/CD y autoscaling (pp.8,22,36-37).

Son opciones de evolucion del alcance inicial; no se consideran implementadas por existir carpetas de infraestructura o dependencias. El orden recomendado tras revisar esta RC es reducir acoplamiento, completar modularidad y verificar portabilidad, y ampliar duracion/volumen de las pruebas de rendimiento, antes de anunciar escalabilidad o disponibilidad productiva.

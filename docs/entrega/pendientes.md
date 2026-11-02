# Pendientes reales y prioridades

Revision: 2 de noviembre de 2026. Matriz vigente: 76 cumplidos, 2 parciales y 0 pendientes de 78. No se incluyen como pendientes los seis defectos iniciales ya corregidos. RNF-01 tiene objetivos medidos en el perfil local, pero no representa un SLA productivo. Kubernetes local queda acreditado por [preparacion-futura.md](../preparacion-futura.md); TLS productivo y portabilidad siguen abiertos.

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
| Cerrado en alcance local | Boton dedicado de vaciado completo del carrito (RF-25) | Dialogo accesible y DELETE /api/cart con confirmacion; prueba visual opcional |
| Cerrado en alcance local | Alta/edicion/borrado de productos, categorias, stock, roles y transiciones de pedidos | Consola GUI administrativa implementada; la API conserva autorización y validación final |
| Parcial | Revision con lector de pantalla, otro navegador y zoom real 200% | Axe, nombres/roles, teclado y zoom 200% automatizados; motores disponibles se registran y falta validacion manual con lector nativo |

No hay recuperacion de contraseña, verificacion de correo o sesion persistente
en navegador; no se presentan como funcionalidades implementadas.

## Obligatorio antes de declarar cumplimiento integral o escalabilidad verificada

La [clasificacion de los ocho parciales](plan-cierre-parciales.md) detalla el
alcance y las pruebas de cierre. RNF-05/06 y RNF-08/21 quedan cerrados en el
alcance local con sus perfiles, contratos y migraciones. Restan dos parciales:
RNF-27 y la validación pública de RNF-15; RF-49 y RNF-07 tienen preparación y
evidencia local verificadas. La portabilidad requiere otro host.

| Orden | Requisito | Falta y accion concreta | Evidencia para cerrar |
| --- | --- | --- | --- |
| Parcial en alcance local | RNF-01, en optimización | La repetición del 2 de noviembre con el índice compuesto registra 0% de errores e invariantes correctas. A 20 usuarios, historial p99 1150,35 ms, checkout p95 1671,00 ms/p99 3390,07 ms superan sus límites; pago p95 1081,58 ms y compra p95 3,921 s cumplen. El diagnóstico SQL/HTTP separado queda dentro de sus objetivos, sin relajar umbrales | [Resultado](../rendimiento/resultado.json), [perfil SQL/HTTP](../perfilado/informe.md). Siguiente paso: optimizar cola/checkout y repetir la aceptación |
| Cerrado en alcance local | RNF-05/06, Cumplido | Overlay aislado; dos instancias de los seis servicios, escalado independiente 2/3/1/2 y compra/cancelacion concurrentes | [Evidencias](../escalabilidad/README.md), incluido benchmark original aprobado; sin garantia productiva |
| 3 / media | RNF-27, Parcial | Ejecutar instalación limpia en un host Linux y otro macOS; ya existen helpers PowerShell/POSIX | [Preparación futura](../preparacion-futura.md) y `tests/frontend_fresh_install.py` |
| 4 / media | RNF-15/49, Parciales | Emitir el certificado público con dominio/DNS/Ingress reales y observar fallo/reparto de réplicas en un entorno real | [Preparación futura](../preparacion-futura.md); configuración cert-manager y Kubernetes local ya están verificadas |

Estos pendientes limitan la afirmacion de cumplimiento del PDF; no se han ocultado como capacidades productivas. Se entrega RC para revision y demostracion mientras siguen abiertos.

## Antes de exponer el sistema o alojar datos reales

| Prioridad | Limite actual | Siguiente trabajo |
| --- | --- | --- |
| Cerrado en alcance local | Persistencia Redis y RabbitMQ | `redis_data` con AOF, `rabbitmq_data` con cookie/Mnesia, backup/restore con hashes SHA-256 y restauración aislada de PostgreSQL/RabbitMQ verificada. Falta custodiar copias fuera del host y validar un restore Redis operativo |
| Alta | Validación pública de HTTPS | Perfil de despliegue con CA pública, renovación, puertos internos cerrados y gestión/rotación; falta ejecutar emisión contra dominio real |
| Cerrado en alcance local | Recuperacion operativa y DLQ manuales | `scripts/verify-backup.*` y `verify-restore-isolated.ps1` restauran y validan dumps SQL, definiciones/Mnesia de RabbitMQ; `alerts.*` vigila RabbitMQ, Redis y Outbox. Falta custodiar copias fuera del host y automatizar reproceso DLQ |
| Cerrado en alcance local | /health de aplicaciones principalmente liveness | `/ready` comprueba DB/Redis/RabbitMQ, Compose lo usa como healthcheck y `scripts/monitor.*`/`alerts.*` informan colas, Outbox y Redis |
| Cerrado en alcance local | Administracion de usuarios/roles y recursos | API y consola GUI para usuarios, productos, categorías, stock y transiciones de pedidos; falta auditoria histórica de cambios |
| Parcial | Dependencias e imágenes reproducibles | Versiones Python fijadas e infraestructura con digests; `scripts/pin-images.*` prepara digests de imágenes propias, pendiente ejecutarlo contra un registro real y fijar transitivas en CI |

## Evolucion opcional para el MVP inicial

- RF-49: balanceo local observado y documentado. La prueba `tests/multinstance_distribution.py` correlaciona 80 solicitudes con `upstream_addr` y confirma tráfico en ambas réplicas. Sigue sin ser una certificación de balanceo productivo, SLA o Kubernetes.
- RNF-07: Kustomize aplicado en Docker Desktop Kubernetes; NetworkPolicies, PDB, alertas y digests de infraestructura preparados. Quedan HA multi-nodo, gestor de secretos y StorageClass redundante reales.
- RNF-15: CA pública, rotación y cierre de HTTP directo configurados; falta emitir/validar el certificado con dominio, DNS, Ingress y cert-manager reales.
- Pasarela real y reembolsos, Elasticsearch, inventario independiente, notificaciones externas, discovery especializado, logs centralizados, Prometheus/Grafana, CI/CD y autoscaling (pp.8,22,36-37).

Son opciones de evolucion del alcance inicial; no se consideran implementadas por existir carpetas de infraestructura o dependencias. El orden recomendado tras revisar esta RC es reducir acoplamiento, completar modularidad y verificar portabilidad, y ampliar duracion/volumen de las pruebas de rendimiento, antes de anunciar escalabilidad o disponibilidad productiva.

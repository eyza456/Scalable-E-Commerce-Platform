# Pendientes reales y prioridades

Revision: 28 de octubre de 2026. Matriz vigente: 69 cumplidos, 9 parciales y 0 pendientes de 78. No se incluyen como pendientes los seis defectos iniciales ya corregidos. RNF-01 ya tiene objetivos y evidencia; permanece parcial porque falla un umbral. La RC etiquetada originalmente tenia 69/8/1; esta es la revision posterior. Los 12 criterios basicos de aceptacion de pp.22-23 tienen evidencia; eso no equivale a cumplir todos los RNF.

## Obligatorio para esta entrega candidata

| Elemento | Criterio de cierre | Estado |
| --- | --- | --- |
| Trazabilidad | Matriz de 78 requisitos con evidencia actual y auditoria anterior preservada | Cerrado |
| Funciones principales | Suite completa, demostracion de nueve pasos y datos de prueba eliminados | Cerrado con evidencia JSON |
| Instalacion | Plantilla de entorno, migracion antes del arranque, esquema limpio y compra comprobados | Cerrado en Windows con Docker Linux |
| Version | Documentacion de limites y etiqueta anotada v0.1.0-rc.1 sobre el commit de entrega | Cierre local; sin remoto configurado |

No hay defectos funcionales conocidos abiertos de la auditoria anterior. La entrega es un candidato del backend MVP, no una declaracion de cumplimiento integral ni un despliegue productivo.

## Obligatorio antes de declarar cumplimiento integral o escalabilidad verificada

| Orden | Requisito | Falta y accion concreta | Evidencia para cerrar |
| --- | --- | --- | --- |
| 1 / alta | RNF-01, Parcial | Outbox optimizado: compra p95 8,205 s cumple 10 s. Ahora perfilar historial (p95 804 ms), checkout (2.894 ms) y pago (2.489 ms), que exceden sus limites a 20 usuarios | Repetir el mismo perfil sin relajar umbrales ni ocultar mayor carga; conservar integridad. [Comparacion](../rendimiento/informe.md) |
| 2 / alta | RNF-05/06, Parcial | Permitir replicas sin nombres/puertos host fijos; probar varias instancias de un servicio y concurrencia entre ellas | Despliegue multinstancia y compra sin duplicados, descuento doble ni errores de enrutamiento |
| 3 / media | RNF-27, Parcial | Ejecutar instalacion limpia en otro host compatible con Docker, Linux y/o macOS | Reporte del mismo fresh_install.py con host/version y resultado; contenedores Linux en Windows no son otro host |
| 4 / media | RNF-08/21, Parcial | Extraer negocio/SQL de routers, mover inicializacion fuera de importaciones y acotar contratos HTTP entre servicios | Pruebas de contrato y regresion conservadas; modulos con responsabilidades claras |

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

- RF-49: balanceo de carga real. Se tiene Nginx con DNS dinamico y prueba de recuperacion; falta demostrar replicas y reparto.
- RNF-07: preparacion/despliegue Kubernetes. Sigue parcial; el PDF excluye la implementacion inicial completa de Kubernetes (p.8).
- RNF-15: HTTPS futuro. Sigue parcial; imprescindible antes de exposicion productiva.
- Pasarela real y reembolsos, Elasticsearch, inventario independiente, notificaciones externas, discovery especializado, logs centralizados, Prometheus/Grafana, CI/CD y autoscaling (pp.8,22,36-37).

Son opciones de evolucion del alcance inicial; no se consideran implementadas por existir carpetas de infraestructura o dependencias. El orden recomendado tras revisar esta RC es reducir las latencias de historial, checkout y pago bajo carga, repetir la medicion, verificar replicas y completar portabilidad, antes de anunciar escalabilidad o disponibilidad productiva.

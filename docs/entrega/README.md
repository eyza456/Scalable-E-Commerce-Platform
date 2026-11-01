# Entrega integrada de backend y frontend

Revision de cierre: 1 de noviembre de 2026. Candidato local del MVP con seis
microservicios, API Gateway y frontend Nexo basado en Stitch. El codigo funcional
de referencia es `e65e84b`; la evidencia integrada y la instalación limpia se ejecutaron sobre la base funcional correspondiente.

## Resultado y alcance

**78 requisitos originales: 74 cumplidos, 4 parciales y 0 pendientes.** La
[matriz principal](../auditoria/matriz-requisitos.md) conserva el alcance del sistema.
La [matriz de cobertura visual](../auditoria/matriz-frontend.md) distingue pantallas,
lectura y operaciones disponibles solo por API. No agrega requisitos al PDF.

El cliente puede registrarse, iniciar sesion, consultar/editar nombre y correo,
buscar productos, gestionar cantidades/items del carrito, crear un pedido,
simular pagos aprobados/rechazados, consultar historial y cancelar cuando procede.
Los precios, stock, importes, permisos y estados los decide el backend.

La consola administrativa visual cubre usuarios/roles y estados de acceso, y el
carrito dispone de vaciado completo con confirmacion. La administracion visual de
productos, categorias, stock y estados de pedidos sigue fuera del alcance. No hay cobros bancarios, envios, cupones,
recuperacion de contraseña ni verificacion por correo.

## Material de entrega

| Material | Contenido |
| --- | --- |
| [Instalacion principal](../../README.md) y [frontend](../../frontend/README.md) | Configuracion, comandos y alcance |
| [Matriz principal](../auditoria/matriz-requisitos.md), [CSV](../auditoria/matriz-requisitos.csv), [JSON](../auditoria/matriz-requisitos.json) | 78 requisitos con codigo, pruebas y enlace a GUI |
| [Cobertura visual](../auditoria/matriz-frontend.md) y [JSON](../auditoria/matriz-frontend.json) | Relacion RF/RNF con pantallas, API y limites |
| [Guion visual completo](../frontend/demostracion-visual.md) | Recorrido cliente, teclado, movil y accesibilidad acotada |
| [Pruebas visuales opcionales](../../tests/frontend_visual_optional.cjs) | Consola administrativa, vaciado, axe, zoom 200% y motores disponibles |
| [Guion API](demostracion.md) y [resultado](demo-resultados.json) | Incluye administracion y vaciado por API |
| [Suite backend](../auditoria/resultado-suite.json) | 164 unittest y escenarios adicionales; cierre actual |
| [Resumen frontend](../auditoria/resultado-frontend.json) | Fechas de 56 escenarios y recorrido; no cambia fechas al revisar |
| [Instalacion completa](../frontend/instalacion-desde-cero.md) | 14 contenedores nuevos, migracion, reinicio y navegador |
| [Rendimiento](../rendimiento/informe.md) | Medicion historica del perfil local, sin repetir carga |
| [Pendientes](pendientes.md) y [notas de esta entrega](notas-entrega-integrada.md) | Limites reales y separacion de evoluciones |
| [Plan de cierre de parciales](plan-cierre-parciales.md) | Clasificacion individual, orden y pruebas de aceptacion de los ocho parciales |
| [Escalabilidad multinstancia](../escalabilidad/README.md) | Seis servicios replicados, escalado independiente y carga sin relajar objetivos |
| [Preparación futura](../preparacion-futura.md) y [Kubernetes](../../k8s/README.md) | Manifiestos Kustomize, TLS local, runner de fallo de réplica e instaladores portables |
| [Operación y recuperación](../operacion-produccion.md) | Persistencia Redis/RabbitMQ, backup/restore, readiness, monitoreo, dependencias fijadas y administración API |
| [Modularidad y contratos](../modularidad.md) y [pagos](../modularidad-pagos.md) | Cuatro etapas de RNF-08/21; checkout, eventos y migraciones versionadas cerrados |
| [Manifiesto](manifiesto-entrega.json) | Hashes de fuentes/documentos/evidencias y referencia Git |

## Instalacion y acceso

Para usar la aplicacion se necesita Docker con contenedores Linux y un navegador.
Node/Playwright/axe y Python del host se requieren para las pruebas adicionales,
no para servir la interfaz.

En una instalacion nueva, crear `.env` desde `.env.example` y reemplazar sus
marcadores siguiendo el README principal. Conservar la configuracion propia si
ya existe. Desde la raiz:

```powershell
docker compose build
docker compose up -d --wait --wait-timeout 180 user-db product-db order-db payment-db redis rabbitmq
docker compose run --rm --no-deps product-service alembic upgrade head
docker compose up -d
docker compose -f docker-compose.yml -f compose.frontend.yml up -d --build frontend
```

- Aplicacion conectada: `http://127.0.0.1:8080/`.
- Gateway/API: `http://127.0.0.1:8000/`.
- Galeria de Stitch, si se levanta aparte en 5173: solo prototipos; no introducir credenciales reales.
- Carrito no reserva stock. El pago simulado aprobado si modifica el inventario local.
- La sesion vive en memoria; recargar/cerrar la pagina exige iniciar sesion nuevamente.

No usar `down -v` para actualizar una instalacion con datos. Los comandos de
instalacion limpia de pruebas crean y eliminan solo su proyecto independiente.

## Reproduccion de verificaciones

Con el backend y frontend activos:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/run_stability.ps1 *> docs/auditoria/suite-pagos-modular.log
$codigoSuite = $LASTEXITCODE
if ($codigoSuite -ne 0) { throw 'La suite backend fallo; revisar el log' }
npm ci --prefix tests/browser-tools --ignore-scripts --no-audit --no-fund
node tests/frontend_journey.cjs
node tests/frontend_visual_optional.cjs
python -X utf8 tests/frontend_fresh_install.py
```

Los dos ultimos comandos requieren Playwright en `NODE_PATH` y Edge, segun el
guion visual. Los cinco scripts de regresion `frontend_browser.cjs`,
`frontend_commerce.cjs`, `frontend_payments.cjs`, `frontend_orders.cjs` y
`frontend_profile.cjs` suman 56 escenarios; ver los README para sus ajustes.
El runner de instalacion limpia requiere tambien Node/Python en PATH.
No se suman las auditorias axe ni sus verificaciones como si fueran unittest.

Para regenerar las matrices despues de una ejecucion backend aprobada y guardada:

```powershell
python docs/auditoria/generar_auditoria.py --suite-log docs/auditoria/suite-pagos-modular.log --suite-exit-code 0
```

Se necesita pypdf y el PDF original local (ruta configurable con `--pdf`). El
generador revisa resultados y referencias; no ejecuta pruebas ni decide estados.
El codigo de salida debe ser el observado. Archivo de criterios:
`docs/auditoria/criterios-revision.json`.

## Estado de Git y aceptacion

La etiqueta historica `v0.1.0-rc.1` sigue apuntando a la primera RC del backend.
No contiene el frontend actual y no se mueve. Sus [notas originales](notas-version.md)
se conservan. Esta revision integrada se identifica por el commit que contiene
estos documentos; no se inventa una nueva etiqueta ni se publica un despliegue.
No hay remoto configurado ni se ha enviado codigo a un servicio externo.

El MVP es demostrable localmente; no representa cumplimiento integral del PDF ni
operacion productiva. Siguen parciales replicas/balanceo observado, Kubernetes
aplicado en cluster, CA/rotacion HTTPS, acoplamiento/capas y portabilidad a otro
host. La revision automatica de accesibilidad y las pruebas de nombres/roles
orientadas a lector de pantalla no sustituyen una certificacion manual con un
lector nativo.

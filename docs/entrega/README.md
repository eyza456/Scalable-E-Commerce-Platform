# Entrega integrada de backend y frontend

Revision de cierre: 29 de octubre de 2026. Candidato local del MVP con seis
microservicios, API Gateway y frontend Nexo basado en Stitch. El codigo funcional
de referencia es `f94fed0`; el perfil multinstancia adicional conserva ese codigo y aporta configuracion y pruebas nuevas.

## Resultado y alcance

**78 requisitos originales: 72 cumplidos, 6 parciales y 0 pendientes.** La
[matriz principal](../auditoria/matriz-requisitos.md) conserva el alcance del sistema.
La [matriz de cobertura visual](../auditoria/matriz-frontend.md) distingue pantallas,
lectura y operaciones disponibles solo por API. No agrega requisitos al PDF.

El cliente puede registrarse, iniciar sesion, consultar/editar nombre y correo,
buscar productos, gestionar cantidades/items del carrito, crear un pedido,
simular pagos aprobados/rechazados, consultar historial y cancelar cuando procede.
Los precios, stock, importes, permisos y estados los decide el backend.

No hay consola administrativa visual de productos, categorias, roles o estados,
ni boton dedicado de vaciado completo del carrito. Esas operaciones API no se
presentan como pantallas implementadas. No hay cobros bancarios, envios, cupones,
recuperacion de contraseña ni verificacion por correo.

## Material de entrega

| Material | Contenido |
| --- | --- |
| [Instalacion principal](../../README.md) y [frontend](../../frontend/README.md) | Configuracion, comandos y alcance |
| [Matriz principal](../auditoria/matriz-requisitos.md), [CSV](../auditoria/matriz-requisitos.csv), [JSON](../auditoria/matriz-requisitos.json) | 78 requisitos con codigo, pruebas y enlace a GUI |
| [Cobertura visual](../auditoria/matriz-frontend.md) y [JSON](../auditoria/matriz-frontend.json) | Relacion RF/RNF con pantallas, API y limites |
| [Guion visual completo](../frontend/demostracion-visual.md) | Recorrido cliente, teclado, movil y accesibilidad acotada |
| [Guion API](demostracion.md) y [resultado](demo-resultados.json) | Incluye administracion y vaciado por API |
| [Suite backend](../auditoria/resultado-suite.json) | 155 unittest y escenarios adicionales; cierre actual |
| [Resumen frontend](../auditoria/resultado-frontend.json) | Fechas de 56 escenarios y recorrido; no cambia fechas al revisar |
| [Instalacion completa](../frontend/instalacion-desde-cero.md) | 14 contenedores nuevos, migracion, reinicio y navegador |
| [Rendimiento](../rendimiento/informe.md) | Medicion historica del perfil local, sin repetir carga |
| [Pendientes](pendientes.md) y [notas de esta entrega](notas-entrega-integrada.md) | Limites reales y separacion de evoluciones |
| [Plan de cierre de parciales](plan-cierre-parciales.md) | Clasificacion individual, orden y pruebas de aceptacion de los ocho parciales |
| [Escalabilidad multinstancia](../escalabilidad/README.md) | Seis servicios replicados, escalado independiente y carga sin relajar objetivos |
| [Modularidad y contratos](../modularidad.md) | Primera etapa de RNF-08/21; mantienen estado parcial |
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
powershell -NoProfile -ExecutionPolicy Bypass -File tests/run_stability.ps1 *> docs/auditoria/suite-modularidad.log
$codigoSuite = $LASTEXITCODE
if ($codigoSuite -ne 0) { throw 'La suite backend fallo; revisar el log' }
npm ci --prefix tests/browser-tools --ignore-scripts --no-audit --no-fund
node tests/frontend_journey.cjs
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
python docs/auditoria/generar_auditoria.py --suite-log docs/auditoria/suite-modularidad.log --suite-exit-code 0
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
operacion productiva. Siguen parciales replicas/balanceo, Kubernetes futuro,
acoplamiento/capas, HTTPS y portabilidad a otro host. La revision automatica de
accesibilidad no es una certificacion completa ni una prueba con lector de pantalla.

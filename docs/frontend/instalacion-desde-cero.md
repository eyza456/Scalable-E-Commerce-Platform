# Instalacion limpia del backend y frontend

Verificada el 29 de octubre de 2026 en Windows con Docker Desktop y contenedores
Linux. Resultado: **aprobado**, con [evidencia JSON](instalacion-desde-cero.json).
La evidencia anterior de `docs/auditoria/` se conserva como instalacion del backend.

## Reproduccion

Preparar Python, Docker, Node.js, Microsoft Edge y Playwright disponible en
`NODE_PATH`, como en el guion visual. Instalar la dependencia de auditoria fijada:

```powershell
npm ci --prefix tests/browser-tools --ignore-scripts --no-audit --no-fund
python -X utf8 tests/frontend_fresh_install.py
```

El runner crea una copia temporal de los archivos versionados del arbol de trabajo
(incluye archivos preparados en Git). Para una revision con nuevos archivos,
prepararlos en Git antes de ejecutar. No copia `.env`, dependencias locales ni
archivos ignorados; las herramientas de navegador se usan desde el host.
El script detalla por hash los bytes probados de README, configuracion y fuentes.
El commit indicado es la base de Git al iniciar; los hashes identifican tambien
los cambios preparados que se estaban verificando antes del commit final.

La configuracion nace de `.env.example` y genera credenciales independientes.
Se resuelve `docker-compose.yml` y el complemento real `compose.frontend.yml`.
Para coexistir con la instalacion habitual, la prueba elimina nombres fijos y
publicaciones directas, usa una red de proyecto propia y puertos loopback aleatorios
para gateway/frontend. Estas adaptaciones de aislamiento no se presentan como
soporte de replicas del Compose original.

## Comprobaciones ejecutadas

1. Construccion de las ocho imagenes de aplicaciones/gateway/frontend desde la
   copia de fuentes. Se permite la cache normal de Docker; no es un ensayo sin cache.
2. Infraestructura nueva y cuatro volumenes PostgreSQL propios, sin datos locales.
3. Alembic de Product antes de arrancar aplicaciones, upgrade repetido e inspeccion
   del head `b1c5a09e3d72`. User, Order y Payment aplican sus migraciones SQL
   versionadas e idempotentes antes de aceptar trafico.
4. Arranque de 14 contenedores, sin reinicios inesperados iniciales. Health de seis
   APIs, gateway y frontend; `nginx -t`, HTML, CSS y cinco modulos JavaScript.
5. Catalogo inicial vacio, autenticacion por proxy y bloqueo de rutas internas.
   `/.env` y prototipos de Stitch no se sirven desde el frontend conectado.
6. Registro, catalogo/categoria, carrito, pedido, rechazo, aprobacion, reserva
   consumida, tres eventos publicados y notificacion por el gateway nuevo.
7. Reinicio del stack aislado y persistencia de usuarios, productos/categorias,
   pedidos, pagos (incluida fecha final) y carrito Redis. Se vuelve a localizar el
   puerto del frontend y se comprueba que sirve la aplicacion.
8. Recorrido completo desde el frontend nuevo: registro/login, compra, rechazo y
   aprobacion, historial, cancelacion y cambio de correo con nuevo login.
9. Catorce estados revisados con axe, cero incidencias/incompletos, doce pruebas
   de reflow y las verificaciones de teclado del guion visual.
10. Limpieza de las fixtures del navegador y eliminacion exclusiva del proyecto
    temporal, sus imagenes locales y volumenes. El directorio temporal se borra
    solo despues de validar que su ruta absoluta pertenece al workspace `tmp/`.

Los helpers del navegador y de limpieza reciben `TEST_COMPOSE_ARGS` con el proyecto
`fresh-...` propio. Validan ese prefijo antes de ejecutar Docker. En uso normal,
sin esa variable, conservan el Compose habitual. Se conserva el recorrido anterior
de la instalacion habitual con su fecha propia. Esta etapa revalida el recorrido
en el stack nuevo sobre el refactor `dca9138`, incluyendo migraciones versionadas en lifespan.

## Evidencias

- [Resultado de instalacion](instalacion-desde-cero.json): configuracion, esquema,
  compra, reinicio, versiones del host y hashes de los README/fuentes probados.
- [Recorrido sobre el stack nuevo](instalacion-cero/recorrido-accesibilidad.json):
  nueve etapas, 14 estados auditados y verificacion de stock/eventos.
- Capturas de esa instalacion: [carrito](instalacion-cero/carrito-desktop.png),
  [pago](instalacion-cero/pago-aprobado.png), [catalogo movil](instalacion-cero/catalogo-mobile.png)
  e [historial movil](instalacion-cero/historial-mobile.png).
- Log local ignorado por Git: `instalacion-desde-cero.log`; el runner redacta las
  credenciales generadas y no incluye el Compose resuelto con secretos en el informe.

Se comprobaron los IDs, tiempos de arranque y contadores de reinicio de los
contenedores de la instalacion habitual antes/despues: no cambiaron. Las capturas
pertenecen a datos temporales ya eliminados, no al catalogo actual del usuario.

## Limites

Se verifica instalacion limpia en el mismo host Windows, no portabilidad a un
host Linux/macOS (RNF-27 sigue parcial). Reiniciar no prueba durabilidad de Redis
o RabbitMQ al recrear sus contenedores; siguen pendientes los volumenes persistentes
y recuperacion operativa documentados en la entrega. No se verifica produccion,
TLS, replicas, lectores de pantalla o nuevos objetivos de rendimiento.
La instalacion limpia se ejecuto sobre el commit `1cfacff`; la suite integrada y la carga RNF-01 se repitieron por separado y sus resultados estan enlazados en la auditoria y en escalabilidad.

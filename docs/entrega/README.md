# Entrega del backend MVP - v0.1.0-rc.1

Candidato local para revision funcional, fechado el 28 de octubre de 2026. Incluye seis servicios, API Gateway, bases PostgreSQL por dominio, carrito Redis, eventos RabbitMQ y pagos simulados. La version se identifica con la etiqueta Git anotada v0.1.0-rc.1.

## Material de entrega

- [Instalacion y configuracion](../../README.md).
- [Matriz vigente de 78 requisitos](../auditoria/matriz-requisitos.md): 70 cumplidos, 8 parciales y 0 pendientes tras perfilar y optimizar SQL/HTTP; evidencia por archivo/linea. La RC original conserva 69/8/1 en su tag.
- [Pendientes priorizados y limites](pendientes.md).
- [Guion de demostracion](demostracion.md) y [resultado ejecutado](demo-resultados.json).
- [Suite final](../auditoria/resultado-suite.json): 153 unittest y escenarios adicionales, incluida la demostracion.
- [Instalacion desde cero](../auditoria/instalacion-desde-cero.md): infraestructura nueva, Alembic, esquemas, compra, eventos y persistencia tras reinicio.
- [Contrato de checkout](../auditoria/cierre-hallazgos.md), [pagos simulados](../pagos-simulados.md), [API Gateway](../api-gateway.md) y [cancelaciones](../pedidos.md).
- [Notas de version](notas-version.md).

## Complemento frontend posterior a la RC

El arbol actual incorpora la interfaz de cliente basada en Stitch y su
[demostracion visual](../frontend/demostracion-visual.md). La [instalacion limpia
completa](../frontend/instalacion-desde-cero.md) se verifico el 29 de octubre:
14 contenedores, migraciones, reinicio/persistencia y recorrido UI sobre el stack
nuevo. Estas mejoras son posteriores a `v0.1.0-rc.1`; no se modifica esa etiqueta
ni se afirma que la RC original contenga el frontend actual.

## Verificacion por el receptor

Configurar .env desde .env.example y ejecutar los pasos ordenados del README. Con la plataforma activa:

```powershell
powershell -ExecutionPolicy Bypass -File tests/run_stability.ps1
python -X utf8 tests/fresh_install.py
```

El primer comando verifica los servicios actuales con fixtures propios. El segundo crea y elimina un proyecto independiente con credenciales nuevas, volumenes nuevos y puerto aleatorio. La copia del README probada queda identificada por hash en el informe de instalacion.

Para regenerar la matriz se necesita pypdf y acceso al PDF original, no versionado en el repositorio. Despues de ejecutar y guardar el log de una suite aprobada:

```powershell
python docs/auditoria/generar_auditoria.py --pdf "C:\Users\Usuario\Downloads\Plataforma_escalable_comercio_electronico.pdf" --suite-log docs/auditoria/suite-sql-http.log --suite-exit-code 0
```

El generador no ejecuta pruebas. Se debe indicar el codigo observado del runner, no asumirlo. Valida textos, 78 IDs, 153 resultados y enlaces reales. Los criterios de evaluacion se revisan en criterios-revision.json; generar no decide por si solo si un requisito esta cumplido.

## Versionado y publicacion

```powershell
git show v0.1.0-rc.1 --stat
git log --oneline --decorate -5
```

La etiqueta apunta al commit de entrega y el arbol queda limpio. No hay remoto configurado; no se ha publicado ni enviado codigo a ningun servicio externo. Los secretos permanecen fuera de Git.

## Alcance de aceptacion

Los 12 criterios basicos de pp.22-23 del PDF tienen evidencia funcional. Esta RC conserva limites explicitos: rendimiento aprobado solo para el perfil local medido, replicas sin verificar, portabilidad de host incompleta, refactorizacion/acoplamiento parciales y evoluciones de infraestructura. No representa cumplimiento del 100% del PDF, operacion productiva ni una pasarela bancaria real.

## Medicion posterior a la RC

Tras perfilar SQL/HTTP, reutilizar transportes y acortar la lectura del historial, todos los objetivos locales de 1/5/10/20 usuarios del perfil v1 se aprueban. A 20: historial p95 286,88 ms, checkout 770,97 ms, pago 525,38 ms y compra 2,738 s; 122,96 req/s utiles y cero errores. Las 1.051 compras conservaron integridad. RNF-01 se considera cumplido en ese alcance, sin afirmar SLA productivo, otras cargas o grandes volumenes. Consultar [objetivos](../rendimiento/objetivos.md) y [resultados](../rendimiento/informe.md). La etiqueta v0.1.0-rc.1 no se modifica; estas evidencias se guardan en un commit posterior.

El [perfil SQL/HTTP](../perfilado/informe.md) documenta contadores, planes, limites del diagnostico e aislamiento de credenciales. La aceptacion usa el benchmark original sin instrumentacion.

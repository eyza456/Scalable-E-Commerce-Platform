# Entrega del backend MVP - v0.1.0-rc.1

Candidato local para revision funcional, fechado el 28 de octubre de 2026. Incluye seis servicios, API Gateway, bases PostgreSQL por dominio, carrito Redis, eventos RabbitMQ y pagos simulados. La version se identifica con la etiqueta Git anotada v0.1.0-rc.1.

## Material de entrega

- [Instalacion y configuracion](../../README.md).
- [Matriz vigente de 78 requisitos](../auditoria/matriz-requisitos.md): 69 cumplidos, 8 parciales y 1 pendiente; evidencia por archivo/linea.
- [Pendientes priorizados y limites](pendientes.md).
- [Guion de demostracion](demostracion.md) y [resultado ejecutado](demo-resultados.json).
- [Suite final](../auditoria/resultado-suite.json): 124 unittest y escenarios adicionales, incluida la demostracion.
- [Instalacion desde cero](../auditoria/instalacion-desde-cero.md): infraestructura nueva, Alembic, esquemas, compra, eventos y persistencia tras reinicio.
- [Contrato de checkout](../auditoria/cierre-hallazgos.md), [pagos simulados](../pagos-simulados.md), [API Gateway](../api-gateway.md) y [cancelaciones](../pedidos.md).
- [Notas de version](notas-version.md).

## Verificacion por el receptor

Configurar .env desde .env.example y ejecutar los pasos ordenados del README. Con la plataforma activa:

```powershell
powershell -ExecutionPolicy Bypass -File tests/run_stability.ps1
python -X utf8 tests/fresh_install.py
```

El primer comando verifica los servicios actuales con fixtures propios. El segundo crea y elimina un proyecto independiente con credenciales nuevas, volumenes nuevos y puerto aleatorio. La copia del README probada queda identificada por hash en el informe de instalacion.

Para regenerar la matriz se necesita pypdf y acceso al PDF original, no versionado en el repositorio. Despues de ejecutar y guardar el log de una suite aprobada:

```powershell
python docs/auditoria/generar_auditoria.py --pdf "C:\Users\Usuario\Downloads\Plataforma_escalable_comercio_electronico.pdf" --suite-log docs/auditoria/suite-entrega.log --suite-exit-code 0
```

El generador no ejecuta pruebas. Se debe indicar el codigo observado del runner, no asumirlo. Valida textos, 78 IDs, 124 resultados y enlaces reales. Los criterios de evaluacion se revisan en criterios-revision.json; generar no decide por si solo si un requisito esta cumplido.

## Versionado y publicacion

```powershell
git show v0.1.0-rc.1 --stat
git log --oneline --decorate -5
```

La etiqueta apunta al commit de entrega y el arbol queda limpio. No hay remoto configurado; no se ha publicado ni enviado codigo a ningun servicio externo. Los secretos permanecen fuera de Git.

## Alcance de aceptacion

Los 12 criterios basicos de pp.22-23 del PDF tienen evidencia funcional. Esta RC conserva limites explicitos: rendimiento sin medir, replicas sin verificar, portabilidad de host incompleta, refactorizacion/acoplamiento parciales y evoluciones de infraestructura. No representa cumplimiento del 100% del PDF, operacion productiva ni una pasarela bancaria real.

# Demostracion completa del backend

## Preparacion

Arrancar la plataforma siguiendo README. Se requiere Docker Desktop, Python 3.11+ y el gateway local en http://127.0.0.1:8000. Para un gateway en otro puerto configurar GATEWAY_URL; los ayudantes Docker de la demo se ejecutan en el proyecto Compose de la carpeta actual.

Desde la raiz:

```powershell
python -X utf8 tests/demo_release.py
```

No instala bibliotecas Python en el host. Las llamadas de cliente pasan por el gateway. El script crea un usuario, categoria, producto y dos pedidos propios; no usa IDs preexistentes. El fixture administrativo es un JWT efimero generado dentro de Payment con la clave de su entorno, igual que en las pruebas de integracion. No es una interfaz de gestion de roles ni se muestra o guarda ese token.

## Guion para mostrar

| Paso | Accion observada | Resultado esperado |
| --- | --- | --- |
| 1 | Registro, login y actualizacion del nombre | JWT valido y perfil actualizado |
| 2 | Crear categoria/producto y consultar disponibles | Solo producto propio, precio 15 y stock 5 |
| 3 | Agregar, modificar, eliminar item y vaciar carrito | Total 30 para dos unidades, carrito vacio tras cada eliminacion/vaciado |
| 4 | Confirmar dos unidades y repetir Idempotency-Key | Un pedido, total 30; respuesta 201 y luego 200 con mismo ID |
| 5 | Simular card_declined | HTTP 409, CARD_DECLINED, fecha final; pedido PENDING y stock 5 |
| 6 | Reintentar aprobado | Pago PAID; pedido PAID por evento; reserva CONSUMED y stock 3 |
| 7 | Intentar transicion como cliente y luego como admin | Cliente 403; admin PROCESSING -> SHIPPED -> DELIVERED |
| 8 | Crear otro pedido sin pagar y cancelar dos veces | CANCELLED ambas veces; stock permanece 3 |
| 9 | Consultar historial propio y detalles | Un DELIVERED y un CANCELLED |

La cancelacion del paso 8 no tiene reserva porque aun no hubo intento de pago. La liberacion real de una reserva pendiente, su idempotencia y recuperacion se comprueban adicionalmente en tests/smoke_orders.py y la suite completa. El stock se revalida al crear el pedido y se reserva al pagar.

Al terminar se eliminan exclusivamente los datos creados. En caso de fallo despues de crear pedidos se conservan fixtures para diagnostico y se imprime su marcador; no se oculta el fallo.

## Evidencia

[Resultado JSON de los nueve pasos](demo-resultados.json). La demo esta incorporada a tests/run_stability.ps1, por lo que tambien se verifica al ejecutar toda la suite. Es una demostracion por API, no una interfaz web ni un envio logistico real.

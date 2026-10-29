# Demostracion completa del cliente

Revision local del 29 de octubre de 2026. Aplicacion: `http://127.0.0.1:8080/`.
El guion conecta las pantallas basadas en Stitch con el backend real mediante
el API Gateway. No es la galeria de prototipos del puerto 5173.

## Repeticion automatizada y aislada

Requisitos: backend configurado/migrado y activo, frontend construido, Node.js,
Playwright disponible en `NODE_PATH` y Microsoft Edge instalado. Son los mismos
requisitos de las pruebas anteriores, mas axe-core fijado en un lockfile:

```powershell
npm ci --prefix tests/browser-tools --ignore-scripts --no-audit --no-fund
node tests/frontend_journey.cjs
```

`FRONTEND_URL` permite otra URL local y `BROWSER_CHANNEL=chrome` otro navegador
Chromium instalado. Las dependencias de auditoria solo se usan en desarrollo;
no se incluyen en el contenedor ni en los scripts de la aplicacion.

El test prepara un producto propio de cinco unidades, registra una cuenta desde
la interfaz y ejecuta todas las acciones del cliente con controles visibles.
No usa HTTP directo para comprar, pagar, cancelar o editar el perfil. Usa SQL
solo para preparar el producto, verificar importes/stock/eventos y limpiar sus
fixtures. Al terminar espera los eventos/reservas y elimina sus datos.
No modifica productos ni cuentas preexistentes. Las capturas muestran fixtures
temporales que ya no permanecen en el catalogo.

## Guion para presentar en pantalla

Si se hace manualmente, disponer de un producto activo con al menos tres unidades
en el catalogo local. La cuenta y sus compras son reales dentro de este entorno:
anotar los IDs creados para su limpieza controlada. No usar datos bancarios reales.

1. Abrir la aplicacion. Pulsar Tab y Enter para comprobar el enlace Ir al contenido.
2. Ir a Mi cuenta, Crear cuenta, completar nombre/correo/contraseña y registrarse.
   Iniciar sesion con la cuenta creada.
3. Buscar el producto, abrir su detalle y agregar una unidad al carrito.
   En el carrito cambiar a dos unidades y actualizar. El total debe coincidir con
   el precio por dos, usando la respuesta del servidor.
4. Revisar y confirmar el pedido. Elegir fondos insuficientes en Pago simulado y
   enviar. Debe aparecer un rechazo, sin descontar stock ni cerrar el pedido.
5. Elegir Pago aprobado y enviar otro intento explicitamente. Debe aparecer la
   referencia y fecha final; el pedido llegara a Pagado por los eventos del backend.
6. Abrir Mis pedidos y consultar ese pedido. No debe ofrecer cancelar un pago
   confirmado.
7. Crear un segundo pedido sin pagarlo. Abrirlo en Mis pedidos y elegir Cancelar.
   Comprobar Tab/Shift+Tab, salir con Escape sin cancelar y volver a abrir el dialogo.
   Confirmar la cancelacion. El resultado debe llegar a Cancelado; no hay reembolso.
8. Ir a Mi cuenta, Editar perfil, cambiar nombre/correo y guardar. La sesion debe
   continuar. Salir e iniciar sesion con el correo nuevo.
9. Revisar catalogo, historial y perfil en movil. Comprobar el foco visible y que
   los mensajes de error/carga se distingan de una lista vacia.

Para ensayar estos pasos con limpieza automatica y resultados verificables,
preferir el comando anterior. La prueba adicional de error 503 es inyectada en el
navegador, no una caida real del backend, y demuestra el boton de recuperacion.

## Resultado y evidencias

Resultado vigente: [recorrido-accesibilidad.json](recorrido-accesibilidad.json).
Contiene nueve etapas, catorce estados auditados, doce comprobaciones de ancho y
seis verificaciones de teclado/foco. Tambien verifica un pago aprobado, un rechazo,
tres eventos de destino y stock final de tres unidades tras comprar dos de cinco.
Los 56 escenarios de regresion anteriores se ejecutan aparte y mantienen sus JSON.

Capturas revisadas de la misma ejecucion:
[carrito escritorio](demo/carrito-desktop.png), [pago aprobado](demo/pago-aprobado.png),
[catalogo movil](demo/catalogo-mobile.png) e [historial movil](demo/historial-mobile.png).

## Hallazgos corregidos

- La franja superior se integro en la cabecera semantica. Antes, axe identificaba
  contenido fuera de landmarks: [revision inicial](a11y-antes.json).
- Se evita mover el foco a main en la carga inicial; el primer Tab vuelve a ofrecer
  el enlace para saltar al contenido. La navegacion entre vistas si enfoca main.
- Actualizar cantidades conserva el foco del control recreado. Al pagar, guardar
  el perfil o cancelar, el foco pasa a un control/estado util y no se pierde en body.
- El dialogo de cancelacion mantiene Tab entre sus botones y permite Escape,
  devolviendo el foco al disparador. Se preserva la ejecucion que detecto el caso:
  [antes de corregir el dialogo](recorrido-antes-dialogo.json).
- El texto de Mi cuenta diferencia acceso sin sesion de gestion de datos autenticada.

## Alcance de accesibilidad

axe-core 4.14.0 revisa reglas etiquetadas WCAG 2 A/AA, 2.1 A/AA, 2.2 AA y buenas
practicas en los estados registrados. El motor se inyecta desde Playwright; no se
deshabilita CSP de la aplicacion ni se entrega axe a los usuarios. Los resultados
incompletos se registran, no se contabilizan como aprobados automaticamente.

La automatizacion no certifica accesibilidad completa: [axe-core documenta sus
limites y la necesidad de revision manual](https://github.com/dequelabs/axe-core#the-accessibility-rules).
Se revisaron teclado, dialogo, foco visible, menor movimiento, disponibilidad del
titulo sin fuentes remotas y reflow a 320/390/768/1440 px en catalogo/historial/perfil.
No se afirma prueba con lector de pantalla, dispositivo movil fisico, zoom real del
navegador al 200%, todos los navegadores ni condiciones productivas.

## Siguiente cierre

La demostracion valida el recorrido principal del cliente. Para ampliar la entrega:
revision con lector de pantalla y otro navegador, y documentacion final. La
[instalacion limpia con frontend](instalacion-desde-cero.md) ya esta verificada.
Las pantallas administrativas y
los pendientes de replicas, portabilidad y operacion del backend siguen separados.

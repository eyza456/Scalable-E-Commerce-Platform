# Integracion visual: acceso y catalogo

Revision local del 29 de octubre de 2026. Interfaz propia en `frontend/app/`,
basada en la direccion visual de Stitch: marfil, verde bosque, Playfair Display y
Plus Jakarta Sans. Los prototipos originales permanecen en `frontend/stitch/`.

## Funciones conectadas

- Registro mediante `/api/auth/register`, con validacion de contraseña por bytes.
- Inicio de sesion mediante `/api/auth/login` y verificacion en `/api/users/me`.
- Consulta de nombre/correo de la cuenta y cierre de sesion en memoria.
- Catalogo real, categorias, filtros por nombre/disponibilidad/categoria y paginacion.
- Detalle real, precio, disponibilidad, descripcion e imagen con alternativa.
- Estados de carga, vacio, validacion y servicio no disponible.

El frontend Nginx publica `http://127.0.0.1:8080/` y reenvia `/api/` al gateway.
No se modifican las rutas del gateway ni las APIs existentes. La nueva interfaz
se construye mediante el complemento `compose.frontend.yml`.

## Verificacion observada

`tests/frontend_browser.cjs`: **13 escenarios aprobados** en Edge headless usando
el backend y gateway locales reales. Resultado en [integracion.json](integracion.json).
Se validaron filtros, detalle, contenido HTML malicioso como texto, URL de imagen
insegura, vacio, registro/duplicado, contraseña UTF-8 larga, login incorrecto/correcto,
consulta autenticada, cierre de sesion/recarga y ausencia de persistencia del token.
Los errores 503 del catalogo y 401 de verificacion de sesion se inyectaron en el
navegador y estan identificados en el resultado; no prueban una caida real del backend.
Tambien se comprobaron 401 en ruta protegida, 404 en ruta interna y 422 con parametros
invalidos a traves del frontend/gateway. Las fixtures se eliminaron al terminar.

No hubo errores de JavaScript durante los escenarios. Se verifico ausencia de
desbordamiento horizontal del catalogo y acceso a 390 px. Se revisaron capturas de
[catalogo de escritorio](catalogo-desktop.png), [catalogo movil](catalogo-mobile.png)
y [acceso movil](acceso-mobile.png). Muestran fixtures temporales, ya eliminadas;
no representan el contenido actual del catalogo. La configuracion Nginx paso `nginx -t`.

## Limites y siguiente etapa

No se conectaron carrito, checkout, pago simulado, pedidos, cancelaciones ni edicion
de perfil. No hay administracion visual de productos. Esos prototipos no son
funcionalidades integradas. Recargar termina la sesion local; cerrar sesion no
revoca tokens en otros clientes. No hay pagos bancarios reales ni HTTPS productivo.

No se repitio la suite completa de 153 pruebas ni la prueba de carga: este cambio
añade una interfaz separada y sus pruebas especificas. La medicion RNF-01 anterior
corresponde al backend; no mide tiempos de carga o accesibilidad de esta interfaz.
El informe de instalacion limpia del backend es anterior al complemento frontend.

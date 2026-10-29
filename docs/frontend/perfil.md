# Edicion visual del perfil

Revision local del 29 de octubre de 2026. Modulo `frontend/app/profile.js`, en
Mi cuenta (`#cuenta`). Reutiliza `PUT /api/users/me` del backend sin modificarlo.

## Comportamiento

El formulario precarga nombre/correo, permite descartar cambios y envia solo los
campos modificados. Se valida nombre entre 3 y 100 caracteres tras quitar espacios,
correo y limites HTML. El servidor mantiene la validacion final y unicidad.
Un correo duplicado no cambia el perfil mostrado ni elimina el borrador.

Al guardar correctamente se reemplazan el perfil y `access_token` en memoria. Se
verifica que la respuesta corresponda al mismo usuario y contenga un token bearer.
Las solicitudes futuras usan ese token, incluido su correo nuevo. No se interpreta
el contenido del token para autorizar permisos; lo hace el backend.

Si la respuesta se pierde o devuelve 5xx, puede existir un cambio confirmado sin
haber recibido su token. La interfaz cierra sesion local y pide autenticar de nuevo;
no repite el PUT ni mantiene el token anterior como si el cambio hubiera fallado.
La cuenta puede haber cambiado de correo: si el correo sugerido no funciona,
comprobar el anterior. Esto no revoca otros tokens ya emitidos en el backend.

El cierre de sesion borra el borrador. Las respuestas se vinculan al propietario,
token original y generacion local: una respuesta tardia se descarta si se cerro
la sesion o se inicio otra. No se persisten tokens ni datos del borrador en el
almacenamiento del navegador. Los 401 autenticados muestran que la sesion termino.

## Verificacion observada

**10 escenarios nuevos** en `tests/frontend_profile.cjs`: acceso requerido,
precarga/descartar sin PUT, no enviar sin cambios/nombre invalido, correo duplicado,
actualizacion real y token utilizado en la siguiente solicitud protegida, login
con correo nuevo, respuesta perdida, sesion expirada, respuesta tardia tras entrar
con otra cuenta y vista movil con solo dos campos editables.

Las perdidas de respuesta, 401 y retrasos se inyectan en Playwright y estan
identificados. Las actualizaciones y logins normales son reales. Se crean dos
cuentas propias y se eliminan al terminar. Resultado con limpieza y hashes en
[perfil.json](perfil.json). Capturas revisadas de [escritorio](perfil-desktop.png)
y [movil](perfil-mobile.png) con fixtures temporales ya eliminadas.

Regresion: **46 escenarios anteriores**, para un total de **56 escenarios de
navegador**. Incluye acceso/catalogo, carrito/checkout, pagos e historial/cancelacion.
Se ejecutaron tambien **6 pruebas de perfil en PostgreSQL desechable** y
`tests/smoke_profile.py`: concurrencia de correo, unicidad, token renovado, campos
privilegiados protegidos, autenticacion y cuenta ajena intacta. Registro observado
en [perfil-backend.json](perfil-backend.json). No se repitieron la suite completa
historica del backend ni RNF-01.

## Alcance pendiente

Los recorridos principales del cliente ya tienen interfaz conectada. Sigue una
demostracion integral desde el navegador y revision de accesibilidad, teclado y
estados visuales. No hay cambio de contraseña, recuperacion por correo, pantallas
administrativas ni verificacion del correo nuevo: no se presentan como implementados.

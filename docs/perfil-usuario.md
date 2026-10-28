# Actualizacion del perfil

`PUT /users/me` requiere el JWT del usuario. Permite cambiar nombre y correo de la propia cuenta; los campos omitidos conservan su valor.

```http
PUT /users/me
Authorization: Bearer <token>
Content-Type: application/json

{"name":"Nuevo nombre","email":"nuevo@example.com"}
```

La respuesta contiene los campos habituales del perfil y `access_token` / `token_type`. El cliente debe sustituir su token por el renovado: incluye el correo actualizado para los servicios de pedidos, pagos y notificaciones. Los tokens anteriores mantienen su validez hasta expirar; este cambio no implementa revocacion de sesiones.

- `name`: entre 3 y 100 caracteres, recortando espacios externos.
- `email`: correo valido de hasta 150 caracteres. Debe ser unico sin distinguir mayusculas, incluso ante solicitudes concurrentes.
- Campos vacios, null, cuerpo vacio o campos adicionales devuelven 422.
- `id`, `role`, `is_active`, contrasena y hash no pueden modificarse mediante este endpoint.
- Correo ocupado: 409; no se guarda ninguna parte del cambio.
- Token ausente/invalido: 401. Las cuentas desactivadas conservan su bloqueo 403.

La contrasena no cambia. Despues de modificar el correo, se inicia sesion con el nuevo correo y la misma contrasena. Login y registro comparan correos sin distinguir mayusculas. No se agrega verificacion por correo electronico.

## Base de datos

Se verifico que no hubiera duplicados por mayusculas y se aplico localmente `services/user-service/migrations/001_unique_email_lower.sql`. Crea el indice unico `ux_users_email_lower`. En otra instalacion existente, ejecutar este SQL sobre `user_db` antes de admitir cambios de correo. Si existen duplicados, la migracion falla sin modificar usuarios; deben resolverse previamente. Las bases nuevas incorporan el indice desde el modelo.

## Verificacion

Se verificaron seis pruebas nuevas sobre PostgreSQL, dos regresiones de usuarios y el flujo HTTP real. Incluyen actualizacion parcial, JWT renovado, proteccion de otras cuentas y campos privilegiados, correo duplicado y solicitudes concurrentes. Las pruebas usan esquemas separados o registros propios que se limpian al terminar.

```powershell
Get-Content tests/profile_stability.py -Raw | docker compose exec -T user-service python -
python -X utf8 tests/smoke_profile.py
```

Tambien se integraron en `tests/run_stability.ps1`.

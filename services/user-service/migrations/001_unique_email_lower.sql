-- Falla sin modificar registros si existen correos duplicados por mayusculas.
BEGIN;
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_lower ON users (lower(email));
COMMIT;

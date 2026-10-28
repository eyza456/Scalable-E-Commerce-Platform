-- ==========================================================
-- MIGRACION 002: DESTINO DE EVENTOS OUTBOX
-- PAYMENT SERVICE
-- ==========================================================

BEGIN;

ALTER TABLE outbox_events
ADD COLUMN destination VARCHAR(100);

-- La tabla debe estar vacía antes de aplicar NOT NULL.
-- Esta migración se ejecutará después de comprobarlo.

ALTER TABLE outbox_events
ALTER COLUMN destination SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_outbox_events_destination
ON outbox_events (destination);

COMMIT;
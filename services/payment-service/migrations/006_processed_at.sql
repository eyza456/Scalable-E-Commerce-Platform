BEGIN;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
-- No inventar fechas de resolucion para pagos historicos.
COMMIT;

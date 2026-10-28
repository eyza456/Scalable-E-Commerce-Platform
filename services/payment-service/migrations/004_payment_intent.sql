-- Intento durable para recuperar caidas entre reservar inventario y confirmar pago.
BEGIN;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS event_payload JSON;
COMMIT;

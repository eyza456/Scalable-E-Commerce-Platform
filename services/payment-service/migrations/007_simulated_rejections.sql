BEGIN;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS simulation_result VARCHAR(30) NOT NULL DEFAULT 'approved';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS rejection_code VARCHAR(50);
-- Los rechazos anteriores solo se producian por stock insuficiente.
UPDATE payments SET rejection_code = 'INSUFFICIENT_STOCK'
WHERE status = 'REJECTED' AND rejection_code IS NULL;
COMMIT;

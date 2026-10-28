-- Ejecutar sobre instalaciones existentes antes de iniciar el worker.
-- Conserva eventos antiguos y genera una entrega para cada consumidor.
BEGIN;
ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS destination VARCHAR(100);
INSERT INTO outbox_events
    (id, event_type, aggregate_id, payload, status, attempts, created_at,
     published_at, last_error, destination)
SELECT md5(e.id || q.destination), e.event_type, e.aggregate_id, e.payload,
       CASE WHEN e.status = 'PUBLISHED' THEN 'PUBLISHED' ELSE 'PENDING' END,
       e.attempts, e.created_at, e.published_at, e.last_error, q.destination
FROM outbox_events e
CROSS JOIN (VALUES ('order_payment_completed'), ('product_payment_completed')) q(destination)
WHERE e.destination IS NULL
ON CONFLICT (id) DO NOTHING;
UPDATE outbox_events SET destination = 'payment_completed',
    status = CASE WHEN status = 'PUBLISHED' THEN 'PUBLISHED' ELSE 'PENDING' END
WHERE destination IS NULL;
ALTER TABLE outbox_events ALTER COLUMN destination SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_outbox_events_destination ON outbox_events(destination);
COMMIT;

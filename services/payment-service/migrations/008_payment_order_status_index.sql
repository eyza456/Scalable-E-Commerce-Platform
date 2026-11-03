-- Índice compuesto para localizar el intento activo de un pedido.
CREATE INDEX IF NOT EXISTS ix_payments_order_status
    ON payments (order_id, status);

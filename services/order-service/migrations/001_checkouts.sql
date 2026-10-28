BEGIN;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS checkout_id VARCHAR(36);
CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_checkout_id ON orders(checkout_id);
CREATE TABLE IF NOT EXISTS checkouts (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    error_code VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_checkouts_user_id ON checkouts(user_id);
CREATE INDEX IF NOT EXISTS ix_checkouts_state ON checkouts(state);
COMMIT;

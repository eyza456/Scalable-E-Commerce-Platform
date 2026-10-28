-- ==========================================================
-- MIGRACION 001: TRANSACTIONAL OUTBOX
-- PAYMENT SERVICE
-- ==========================================================

BEGIN;

CREATE TABLE IF NOT EXISTS outbox_events (

    id VARCHAR(36) PRIMARY KEY,

    event_type VARCHAR(100) NOT NULL,

    aggregate_id INTEGER NOT NULL,

    payload JSON NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    attempts INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    published_at TIMESTAMPTZ NULL,

    last_error TEXT NULL,

    CONSTRAINT ck_outbox_status
        CHECK (
            status IN (
                'PENDING',
                'PROCESSING',
                'PUBLISHED'
            )
        ),

    CONSTRAINT ck_outbox_attempts
        CHECK (attempts >= 0)

);

CREATE INDEX IF NOT EXISTS ix_outbox_events_aggregate_id
    ON outbox_events (aggregate_id);

CREATE INDEX IF NOT EXISTS ix_outbox_events_status
    ON outbox_events (status);

COMMIT;
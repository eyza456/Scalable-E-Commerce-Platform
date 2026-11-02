-- Índice compuesto para el historial paginado por usuario.
-- Mantiene el filtro y el orden de list_orders/list_all sin ordenar todo el conjunto.
CREATE INDEX IF NOT EXISTS ix_orders_user_created_id
    ON orders (user_id, created_at DESC, id DESC);

import logging
from datetime import datetime, timezone

from app.core.rabbitmq import publish_event
from app.database import SessionLocal
from app.models import OutboxEvent

logger = logging.getLogger(__name__)
BATCH_SIZE = 50
RETRY_INTERVAL_SECONDS = 5


def dispatch_pending():
    """Entrega al menos una vez; devuelve entregas publicadas y confirmadas en DB."""
    with SessionLocal() as db:
        events = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.status == "PENDING")
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .with_for_update(skip_locked=True)
            .limit(BATCH_SIZE)
            .all()
        )
        published = 0
        for event in events:
            event.attempts += 1
            try:
                publish_event(event.destination, event.payload, event.id)
            except Exception as exc:
                event.last_error = str(exc)[:2000]
                logger.warning("Outbox %s pendiente: %s", event.id, exc)
            else:
                event.status = "PUBLISHED"
                event.published_at = datetime.now(timezone.utc)
                event.last_error = None
                published += 1
        db.commit()
        return published


def run_outbox(stop):
    while not stop.is_set():
        try:
            if dispatch_pending() == BATCH_SIZE:
                # Hay progreso sin fallos: drenar el siguiente lote ahora.
                # Los fallos devuelven menos de BATCH_SIZE y conservan backoff.
                continue
        except Exception:
            logger.exception("Fallo del worker Outbox; se reintentara")
        stop.wait(RETRY_INTERVAL_SECONDS)

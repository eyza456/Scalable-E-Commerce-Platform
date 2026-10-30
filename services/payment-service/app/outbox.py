import logging
from datetime import datetime, timezone
from dataclasses import dataclass

from app.core.rabbitmq import publisher_batch
from app.database import SessionLocal
from app import payment_repository as repository

logger = logging.getLogger(__name__)
BATCH_SIZE = 50
RETRY_INTERVAL_SECONDS = 5
IDLE_INTERVAL_SECONDS = 1


@dataclass(frozen=True)
class DispatchResult:
    selected: int
    published: int

    @property
    def failed(self):
        return self.selected - self.published


def dispatch_pending():
    """Entrega al menos una vez; informa progreso confirmado en DB y filas fallidas."""
    with SessionLocal() as db:
        events = repository.pending_events(db, BATCH_SIZE)
        published = 0
        with publisher_batch() as publish:
            for event in events:
                event.attempts += 1
                try:
                    publish(event.destination, event.payload, event.id)
                except Exception as exc:
                    event.last_error = str(exc)[:2000]
                    logger.warning("Outbox %s pendiente: %s", event.id, exc)
                else:
                    event.status = "PUBLISHED"
                    event.published_at = datetime.now(timezone.utc)
                    event.last_error = None
                    published += 1
        db.commit()
        return DispatchResult(len(events), published)


def run_outbox(stop):
    while not stop.is_set():
        delay = RETRY_INTERVAL_SECONDS
        try:
            result = dispatch_pending()
            if result.failed == 0:
                if result.selected:
                    # Cualquier lote sano puede tener mas trabajo detras.
                    continue
                delay = IDLE_INTERVAL_SECONDS
        except Exception:
            logger.exception("Fallo del worker Outbox; se reintentara")
        stop.wait(delay)

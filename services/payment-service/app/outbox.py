import logging
from datetime import datetime, timezone

from app.core.rabbitmq import publish_event
from app.database import SessionLocal
from app.models import OutboxEvent

logger = logging.getLogger(__name__)


def dispatch_pending():
    """Entrega al menos una vez; los consumidores deben tolerar duplicados."""
    with SessionLocal() as db:
        events = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.status == "PENDING")
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .with_for_update(skip_locked=True)
            .limit(50)
            .all()
        )
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
        db.commit()
        return len(events)


def run_outbox(stop):
    while not stop.is_set():
        try:
            dispatch_pending()
        except Exception:
            logger.exception("Fallo del worker Outbox; se reintentara")
        stop.wait(5)

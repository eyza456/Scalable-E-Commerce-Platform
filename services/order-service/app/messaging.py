"""Topologia reproducible: reintentos con espera y DLQ sin politicas externas."""
import pika

PREFIX = "order"
QUEUE = f"{PREFIX}_payment_completed"
RETRY_EXCHANGE = f"{PREFIX}_payment_retry_exchange"
RETRY_KEY = f"{PREFIX}_payment_retry"
RETRY_QUEUE = f"{PREFIX}_payment_retry_queue"
DLQ = f"{PREFIX}_payment_completed_dlq"
ATTEMPT_HEADER = f"x-{PREFIX}-attempt"
MAX_ATTEMPTS = 3


def declare_topology(ch):
    ch.confirm_delivery()
    ch.queue_declare(queue=QUEUE, durable=True)
    ch.queue_declare(queue=DLQ, durable=True)
    ch.exchange_declare(exchange=RETRY_EXCHANGE, exchange_type="direct", durable=True)
    ch.queue_declare(queue=RETRY_QUEUE, durable=True, arguments={
        "x-message-ttl": 5000,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": QUEUE,
    })
    ch.queue_bind(exchange=RETRY_EXCHANGE, queue=RETRY_QUEUE, routing_key=RETRY_KEY)


def forward(ch, method, properties, body, temporary):
    headers = dict(getattr(properties, "headers", None) or {})
    try:
        attempt = max(1, int(headers.get(ATTEMPT_HEADER, 1)))
    except (ValueError, TypeError):
        attempt = 1
    retry = temporary and attempt < MAX_ATTEMPTS
    headers[ATTEMPT_HEADER] = attempt + 1
    confirmed = ch.basic_publish(
        exchange=RETRY_EXCHANGE if retry else "",
        routing_key=RETRY_KEY if retry else DLQ,
        body=body,
        properties=pika.BasicProperties(
            content_type="application/json", delivery_mode=2,
            headers=headers, message_id=getattr(properties, "message_id", None),
        ),
        mandatory=True,
    )
    # BlockingChannel devuelve None tras Basic.Ack y lanza excepcion ante Nack/Return.
    if confirmed is False:
        raise RuntimeError("RabbitMQ no confirmo el reintento o la DLQ")
    # Si publicar falla no confirmar el original: se recupera al reconectar.
    ch.basic_ack(delivery_tag=method.delivery_tag)

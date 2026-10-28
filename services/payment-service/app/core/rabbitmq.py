import json
import os
import pika

PAYMENT_QUEUES = ("payment_completed", "order_payment_completed", "product_payment_completed")


def publish_event(destination, message, event_id):
    """Publica una entrega persistente y exige confirmacion del broker."""
    if destination not in PAYMENT_QUEUES:
        raise ValueError("Destino desconocido")
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        heartbeat=30, socket_timeout=5, stack_timeout=10,
        blocked_connection_timeout=5,
    ))
    try:
        channel = connection.channel()
        channel.queue_declare(queue=destination, durable=True)
        channel.confirm_delivery()
        confirmed = channel.basic_publish(
            exchange="", routing_key=destination,
            body=json.dumps(message).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json", delivery_mode=2, message_id=event_id,
            ),
            mandatory=True,
        )
        # BlockingChannel devuelve None tras Basic.Ack y lanza excepcion ante Nack/Return.
        if confirmed is False:
            raise RuntimeError("RabbitMQ no confirmo la entrega")
    finally:
        if connection.is_open:
            connection.close()

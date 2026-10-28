import json
import os
from contextlib import contextmanager
import pika

PAYMENT_QUEUES = ("payment_completed", "order_payment_completed", "product_payment_completed")


@contextmanager
def publisher_batch():
    """Conexion/canal exclusivos del lote; ACK por mensaje, sin compartir hilos."""
    connection = channel = None
    setup_error = None
    declared = set()

    def send(destination, message, event_id):
        nonlocal connection, channel, setup_error
        if destination not in PAYMENT_QUEUES:
            raise ValueError("Destino desconocido")
        if setup_error is not None:
            # Una conexion fallida por lote: no martillar al broker por cada fila.
            raise setup_error
        if channel is None:
            try:
                connection = pika.BlockingConnection(pika.ConnectionParameters(
                    host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
                    port=int(os.getenv("RABBITMQ_PORT", "5672")),
                    heartbeat=30, socket_timeout=5, stack_timeout=10,
                    blocked_connection_timeout=5,
                ))
                channel = connection.channel()
                channel.confirm_delivery()
            except Exception as exc:
                setup_error = exc
                raise
        if destination not in declared:
            channel.queue_declare(queue=destination, durable=True)
            declared.add(destination)
        confirmed = channel.basic_publish(
            exchange="", routing_key=destination,
            body=json.dumps(message).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json", delivery_mode=2, message_id=event_id,
            ),
            mandatory=True,
        )
        # BlockingChannel devuelve None tras ACK y lanza excepcion ante NACK/Return.
        if confirmed is False:
            raise RuntimeError("RabbitMQ no confirmo la entrega")

    try:
        yield send
    finally:
        if connection is not None and connection.is_open:
            connection.close()


def publish_event(destination, message, event_id):
    """Publicacion individual con el mismo contrato de ACK y persistencia."""
    if destination not in PAYMENT_QUEUES:
        raise ValueError("Destino desconocido")
    with publisher_batch() as send:
        send(destination, message, event_id)

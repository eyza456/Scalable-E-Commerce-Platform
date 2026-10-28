"""Comprueba TTL, redelivery y DLQ en RabbitMQ con colas exclusivas de prueba."""
import os
import time
import uuid

import pika
from app import messaging


def main():
    prefix = "test_stability_" + uuid.uuid4().hex
    names = {
        "QUEUE": prefix + "_main", "RETRY_QUEUE": prefix + "_retry",
        "RETRY_EXCHANGE": prefix + "_exchange", "RETRY_KEY": prefix + "_key",
        "DLQ": prefix + "_dlq",
    }
    for name, value in names.items():
        setattr(messaging, name, value)
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
    ))
    ch = connection.channel()
    try:
        messaging.declare_topology(ch)
        ch.basic_publish(exchange="", routing_key=messaging.QUEUE, body=b'{"test":true}',
                         properties=pika.BasicProperties(delivery_mode=2), mandatory=True)
        method, properties, body = ch.basic_get(queue=messaging.QUEUE, auto_ack=False)
        assert method is not None
        messaging.forward(ch, method, properties, body, temporary=True)
        deadline = time.monotonic() + 12
        while True:
            method, properties, body = ch.basic_get(queue=messaging.QUEUE, auto_ack=False)
            if method:
                break
            assert time.monotonic() < deadline, "El mensaje no regreso de la cola TTL"
            connection.sleep(0.1)
        assert properties.headers[messaging.ATTEMPT_HEADER] == 2
        properties.headers[messaging.ATTEMPT_HEADER] = messaging.MAX_ATTEMPTS
        messaging.forward(ch, method, properties, body, temporary=True)
        method, properties, body = ch.basic_get(queue=messaging.DLQ, auto_ack=False)
        assert method is not None and body == b'{"test":true}'
        ch.basic_ack(method.delivery_tag)
        print("OK: reintento TTL y DLQ reales para", messaging.PREFIX)
    finally:
        if ch.is_open:
            for name in ("QUEUE", "RETRY_QUEUE", "DLQ"):
                target = names[name]
                assert target.startswith(prefix)
                ch.queue_delete(queue=target)
            ch.exchange_delete(exchange=names["RETRY_EXCHANGE"])
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    main()


import json
import os
import pika


RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
DLQ_NAME = "product_payment_completed_dlq"


def inspect_dlq():

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST
        )
    )

    channel = connection.channel()

    try:
        method, properties, body = channel.basic_get(
            queue=DLQ_NAME,
            auto_ack=False
        )

        if method is None:
            print("La Dead Letter Queue esta vacia")
            return

        print("\n=== MENSAJE FALLIDO ===")

        try:
            message = json.loads(body.decode("utf-8"))
            print(json.dumps(message, indent=4))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print("Contenido no JSON:", repr(body))

        print("\n=== METADATOS ===")

        print("Exchange:", method.exchange)
        print("Routing key:", method.routing_key)

        headers = properties.headers or {}

        print(
            json.dumps(
                headers,
                indent=4,
                default=str
            )
        )

        # Conservar el mensaje en la DLQ
        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=True
        )

        print("\nMensaje conservado en la DLQ")

    finally:
        connection.close()


if __name__ == "__main__":
    inspect_dlq()

import json
import os
import time

import pika


RABBITMQ_HOST = os.getenv(
    "RABBITMQ_HOST",
    "rabbitmq"
)

RABBITMQ_PORT = int(
    os.getenv(
        "RABBITMQ_PORT",
        "5672"
    )
)


def process_payment_notification(message: dict):

    print("====================================", flush=True)
    print("NOTIFICACIÓN RECIBIDA", flush=True)
    print("====================================", flush=True)

    print(f"Evento: {message.get('event')}", flush=True)
    print(f"Orden: #{message.get('order_id')}", flush=True)
    print(f"Usuario: {message.get('user_id')}", flush=True)
    print(f"Email: {message.get('email')}", flush=True)
    print(f"Monto: ${message.get('amount')}", flush=True)
    print(
        f"Transacción: {message.get('transaction_id')}",
        flush=True
    )

    print("====================================", flush=True)


def callback(ch, method, properties, body):

    try:

        message = json.loads(
            body.decode("utf-8")
        )

        process_payment_notification(
            message
        )

        ch.basic_ack(
            delivery_tag=method.delivery_tag
        )

    except Exception as e:

        print(
            f"Error procesando notificación: {e}"
        )

        ch.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=False
        )


def start_consumer():

    while True:

        try:

            print(
                f"Intentando conectar a RabbitMQ "
                f"{RABBITMQ_HOST}:{RABBITMQ_PORT}..."
            )

            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT
                )
            )

            channel = connection.channel()

            channel.queue_declare(
                queue="payment_completed",
                durable=True
            )

            channel.basic_qos(
                prefetch_count=1
            )

            channel.basic_consume(
                queue="payment_completed",
                on_message_callback=callback
            )

            print(
                "===================================="
            )

            print(
                "Notification Service conectado a RabbitMQ"
            )

            print(
                "Esperando eventos PAYMENT_COMPLETED..."
            )

            print(
                "===================================="
            )

            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:

            print(
                f"No se pudo conectar a RabbitMQ: {e}"
            )

            print(
                "Reintentando en 5 segundos..."
            )

            time.sleep(5)

        except Exception as e:

            print(
                f"Error en consumidor RabbitMQ: {e}"
            )

            print(
                "Reintentando en 5 segundos..."
            )

            time.sleep(5)
import json
import os
import time

import pika
from app.messaging import declare_topology, forward

from sqlalchemy.exc import (
    OperationalError,
    InterfaceError,
    DisconnectionError,
    TimeoutError as SQLAlchemyTimeoutError,
)

from app.database import SessionLocal
from app.models import Order

from app.services.payment_validation import (
    verify_payment_event,
    PermanentValidationError,
    TemporaryValidationError,
)


# ==========================================================
# CONFIGURACION RABBITMQ
# ==========================================================

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))

QUEUE_NAME = "order_payment_completed"


# ==========================================================
# PROCESAR EVENTO PAYMENT_COMPLETED
# ==========================================================


def process_payment_completed(message: dict):
    """
    Valida un pago contra Payment Service y actualiza
    una orden exclusivamente de PENDING a PAID.

    No modifica ordenes que ya esten en PAID,
    PROCESSING, SHIPPED o DELIVERED.
    """

    if not isinstance(message, dict):
        raise PermanentValidationError("El evento debe ser un objeto JSON")

    order_id = message.get("order_id")

    if type(order_id) is not int or order_id <= 0:
        raise PermanentValidationError("order_id invalido")

    db = SessionLocal()

    try:
        # Consultar la orden sin bloquearla durante la llamada HTTP.
        order = db.query(Order).filter(Order.id == order_id).first()

        if order is None:
            raise PermanentValidationError(f"La orden {order_id} no existe")

        # Guardar los datos necesarios para la validacion.
        # Evitamos mantener abierta una transaccion de lectura
        # durante la solicitud HTTP.
        from types import SimpleNamespace

        order_snapshot = SimpleNamespace(
            id=order.id,
            user_id=order.user_id,
            total=order.total,
        )

        db.rollback()

        # Verificar la autenticidad del pago contra Payment Service.
        verify_payment_event(message, order_snapshot)

        # Bloquear la orden antes de actualizarla.
        order = db.query(Order).filter(Order.id == order_id).with_for_update().first()

        if order is None:
            raise PermanentValidationError(f"La orden {order_id} ya no existe")

        # Verificar nuevamente los datos relevantes.
        if (
            order.user_id != order_snapshot.user_id
            or order.total != order_snapshot.total
        ):
            raise PermanentValidationError(
                "Los datos de la orden cambiaron durante la validacion"
            )

        print("====================================")
        print("PAYMENT_COMPLETED VALIDADO")
        print(f"Orden: {order_id}")
        print(f"Estado actual: {order.status}")
        print("====================================")

        # Idempotencia: nunca retroceder estados.
        if order.status in (
            "PAID",
            "PROCESSING",
            "SHIPPED",
            "DELIVERED",
        ):
            print(
                f"Orden {order_id}: evento duplicado verificado. "
                "No se realizaron cambios."
            )

            db.rollback()
            return

        if order.status == "CANCELLING":
            raise TemporaryValidationError(
                "Cancelacion en curso; esperar la decision de Payment"
            )

        # Un pago solamente puede pasar PENDING -> PAID.
        if order.status != "PENDING":
            raise PermanentValidationError(
                f"Transicion no permitida: {order.status} -> PAID"
            )

        order.status = "PAID"

        db.commit()

        print(f"Orden {order_id} actualizada correctamente a PAID")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==========================================================
# PUBLICAR MENSAJE DE REINTENTO
# ==========================================================


def callback(ch, method, properties, body):
    try:
        message = json.loads(body.decode("utf-8"))
        process_payment_completed(message)
    except (
        TemporaryValidationError,
        OperationalError,
        InterfaceError,
        DisconnectionError,
        SQLAlchemyTimeoutError,
    ) as exc:
        print(f"Error temporal: {exc}", flush=True)
        forward(ch, method, properties, body, temporary=True)
    except (PermanentValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"Evento rechazado: {exc}", flush=True)
        forward(ch, method, properties, body, temporary=False)
    else:
        ch.basic_ack(delivery_tag=method.delivery_tag)


def start_consumer(stop=None):
    """
    Mantiene activo el consumidor de eventos de pago.
    """

    while stop is None or not stop.is_set():

        connection = None

        try:
            print("====================================")
            print("INICIANDO ORDER SERVICE CONSUMER")
            print(f"RabbitMQ: {RABBITMQ_HOST}:{RABBITMQ_PORT}")
            print(f"Cola: {QUEUE_NAME}")
            print("====================================")

            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    heartbeat=60,
                    blocked_connection_timeout=30,
                )
            )

            channel = connection.channel()
            declare_topology(channel)

            # Habilitar confirmaciones de publicacion.
            channel.confirm_delivery()

            # Declarar la cola principal.
            channel.queue_declare(
                queue=QUEUE_NAME,
                durable=True,
            )

            # Procesar un mensaje a la vez.
            channel.basic_qos(prefetch_count=1)

            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=callback,
                auto_ack=False,
            )

            print("Order Service conectado a RabbitMQ")
            print("Esperando eventos PAYMENT_COMPLETED...")

            if stop is None:
                channel.start_consuming()
            else:
                while not stop.is_set():
                    connection.process_data_events(time_limit=1)

        except Exception as exc:

            print(f"Error en consumidor RabbitMQ: {exc}")

        finally:

            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass

        print("Reintentando conexion en 5 segundos...")
        if stop is None:
            time.sleep(5)
        else:
            stop.wait(5)

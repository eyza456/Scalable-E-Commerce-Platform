
import json
import os
import time

import pika
from app.messaging import declare_topology, forward
from sqlalchemy import update
from sqlalchemy.exc import (IntegrityError, OperationalError, InterfaceError, DisconnectionError, TimeoutError as SQLAlchemyTimeoutError)

from app.database import SessionLocal
from app.models import Product, ProcessedPaymentEvent
from app.reservations import consume
from app.services.payment_validation import (
    verify_payment_and_order,
    TemporaryValidationError
)

# ==========================================
# CONFIGURACION DE RABBITMQ
# ==========================================

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))

QUEUE_NAME = "product_payment_completed"

DLX_NAME = "product_payment_dlx"
DLQ_NAME = "product_payment_completed_dlq"
DLQ_ROUTING_KEY = "product_payment_failed"


# ==========================================
# PROCESAR EVENTO PAYMENT_COMPLETED
# ==========================================

def process_payment_completed(message: dict):
    """
    Procesa un pago confirmado y descuenta
    el inventario de manera atomica.
    """

    if not isinstance(message, dict):
        raise ValueError("El evento debe ser un objeto JSON")

    if message.get("event") != "PAYMENT_COMPLETED":
        raise ValueError("Tipo de evento incorrecto")

    order_id = message.get("order_id")
    transaction_id = message.get("transaction_id")
    items = message.get("items")

    print("====================================")
    print("EVENTO PAYMENT_COMPLETED RECIBIDO")
    print(f"Orden: #{order_id}")
    print(f"Transaccion: {transaction_id}")
    print("====================================")

    # Validar datos generales del evento
    if (
        type(order_id) is not int
        or order_id <= 0
        or not isinstance(transaction_id, str)
        or not transaction_id.strip()
        or not isinstance(items, list)
        or not items
    ):
        raise ValueError("Evento PAYMENT_COMPLETED invalido")

    # Agrupar cantidades por producto
    normalized_items = {}

    for item in items:

        if not isinstance(item, dict):
            raise ValueError("Item invalido")

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if (
            type(product_id) is not int
            or product_id <= 0
            or type(quantity) is not int
            or quantity <= 0
        ):
            raise ValueError(
                "Producto o cantidad invalida"
            )

        normalized_items[product_id] = (
            normalized_items.get(product_id, 0)
            + quantity
        )
    # ==========================================
    # VERIFICAR AUTENTICIDAD DEL EVENTO
    # ==========================================

    verified, reason = verify_payment_and_order(message)

    if not verified:
        raise ValueError(
            f"Evento PAYMENT_COMPLETED no autorizado: {reason}"
        )

    print("VALIDACION DE SEGURIDAD:")
    print(reason)

    db = SessionLocal()

    try:

        # Registrar transaccion para idempotencia.
        # Debe existir una restriccion UNIQUE
        # sobre transaction_id en PostgreSQL.
        processed_event = ProcessedPaymentEvent(
            transaction_id=transaction_id,
            order_id=order_id
        )

        db.add(processed_event)

        # Detectar duplicados antes del descuento
        db.flush()

        if message.get("inventory_reservation_id"):
            consume(db, message, normalized_items)
        else:
            # Compatibilidad con pagos historicos anteriores a las reservas.
            # Descontar inventario
            for product_id, quantity in sorted(
                normalized_items.items()
            ):

                result = db.execute(
                    update(Product)
                    .where(
                        Product.id == product_id,
                        Product.stock >= quantity
                    )
                    .values(
                        stock=Product.stock - quantity
                    )
                )

                if result.rowcount != 1:
                    raise ValueError(
                        f"Producto #{product_id} inexistente "
                        f"o stock insuficiente"
                    )

                print(
                    f"Producto #{product_id}: "
                    f"-{quantity} unidades"
                )

        # Confirmar registro y descuento juntos
        db.commit()

        print(
            f"Pago {transaction_id} "
            "procesado correctamente"
        )

    
    except IntegrityError:

        db.rollback()

        # Buscar si la transaccion ya fue procesada
        existing_transaction = (
            db.query(ProcessedPaymentEvent)
            .filter_by(transaction_id=transaction_id)
            .first()
        )

        if existing_transaction:

            if existing_transaction.order_id == order_id:
                print(
                    f"[IDEMPOTENCIA] Transaccion duplicada: "
                    f"{transaction_id}. No se descuenta stock.",
                    flush=True
                )
                return

            raise ValueError(
                f"Conflicto de seguridad: la transaccion "
                f"{transaction_id} ya pertenece a la orden "
                f"{existing_transaction.order_id}"
            )

        # Buscar si la orden ya fue procesada
        existing_order = (
            db.query(ProcessedPaymentEvent)
            .filter_by(order_id=order_id)
            .first()
        )

        if existing_order:

            raise ValueError(
                f"Conflicto de idempotencia: la orden #{order_id} "
                f"ya fue procesada con la transaccion "
                f"{existing_order.transaction_id}"
            )

        # Error de integridad desconocido
        raise

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()


# ==========================================
# CALLBACK DE RABBITMQ
# ==========================================


def callback(ch, method, properties, body):
    try:
        message = json.loads(body.decode("utf-8"))
        process_payment_completed(message)
    except (TemporaryValidationError, OperationalError, InterfaceError, DisconnectionError, SQLAlchemyTimeoutError) as exc:
        print(f"Error temporal: {exc}", flush=True)
        forward(ch, method, properties, body, temporary=True)
    except (ValueError, UnicodeDecodeError) as exc:
        print(f"Evento rechazado: {exc}", flush=True)
        forward(ch, method, properties, body, temporary=False)
    else:
        ch.basic_ack(delivery_tag=method.delivery_tag)


def start_consumer():
    """
    Mantiene el consumidor conectado a RabbitMQ.
    Si la conexion falla, intenta reconectarse.
    """

    while True:

        connection = None

        try:

            print(
                f"Intentando conectar a RabbitMQ "
                f"{RABBITMQ_HOST}:{RABBITMQ_PORT}..."
            )

            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    heartbeat=60,
                    blocked_connection_timeout=300
                )
            )

            channel = connection.channel()
            declare_topology(channel)

            # Crear Dead Letter Exchange
            channel.exchange_declare(
                exchange=DLX_NAME,
                exchange_type="direct",
                durable=True
            )

            # Crear Dead Letter Queue
            channel.queue_declare(
                queue=DLQ_NAME,
                durable=True
            )

            # Asociar DLQ con DLX
            channel.queue_bind(
                exchange=DLX_NAME,
                queue=DLQ_NAME,
                routing_key=DLQ_ROUTING_KEY
            )

            # Crear o verificar cola principal
            # El DLX se configura mediante
            # una politica existente de RabbitMQ.
            channel.queue_declare(
                queue=QUEUE_NAME,
                durable=True
            )

            # Procesar un mensaje a la vez
            channel.basic_qos(
                prefetch_count=1
            )

            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=callback,
                auto_ack=False
            )

            print("====================================")
            print("Product Service conectado a RabbitMQ")
            print(
                "Esperando eventos PAYMENT_COMPLETED "
                f"en {QUEUE_NAME}..."
            )
            print("====================================")

            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as exc:

            print(
                f"Error de conexion RabbitMQ: {exc}"
            )

        except Exception as exc:

            print(
                f"Error en consumidor RabbitMQ: {exc}"
            )

        finally:

            if connection and connection.is_open:
                connection.close()

        print(
            "Reintentando conexion en 5 segundos..."
        )

        time.sleep(5)

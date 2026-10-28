
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import pika

from app.database import SessionLocal
from app.models import ProcessedPaymentEvent


# ==========================================
# CONFIGURACION
# ==========================================

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))

DLQ_NAME = "product_payment_completed_dlq"


# ==========================================
# 1. VALIDACION DEL EVENTO
# ==========================================

def validate_event(message):
    """Valida la estructura de PAYMENT_COMPLETED."""

    if not isinstance(message, dict):
        return False, "El mensaje no es un objeto JSON"

    if message.get("event") != "PAYMENT_COMPLETED":
        return False, "Tipo de evento incorrecto"

    order_id = message.get("order_id")
    transaction_id = message.get("transaction_id")
    items = message.get("items")

    if type(order_id) is not int or order_id <= 0:
        return False, "order_id invalido"

    if (
        not isinstance(transaction_id, str)
        or not transaction_id.strip()
    ):
        return False, "transaction_id invalido"

    if not isinstance(items, list) or not items:
        return False, "La lista de productos esta vacia o es invalida"

    for item in items:
        if not isinstance(item, dict):
            return False, "Item invalido"

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if type(product_id) is not int or product_id <= 0:
            return False, "product_id invalido"

        if type(quantity) is not int or quantity <= 0:
            return False, (
                f"Cantidad invalida para producto #{product_id}: "
                f"{quantity}"
            )

    return True, "Estructura valida"


# ==========================================
# 2. VERIFICACION DE IDEMPOTENCIA
# ==========================================


def check_processed(transaction_id, order_id):
    """
    Comprueba la idempotencia por transaccion y orden.

    No modifica registros.
    """

    db = SessionLocal()

    try:
        existing_transaction = (
            db.query(ProcessedPaymentEvent)
            .filter_by(transaction_id=transaction_id)
            .first()
        )

        if existing_transaction:
            if existing_transaction.order_id == order_id:
                return (
                    False,
                    "La transaccion ya fue procesada para esta orden"
                )

            return (
                False,
                "Conflicto: la transaccion pertenece a otra orden"
            )

        existing_order = (
            db.query(ProcessedPaymentEvent)
            .filter_by(order_id=order_id)
            .first()
        )

        if existing_order:
            return (
                False,
                "Conflicto: la orden ya tiene otra transaccion procesada"
            )

        return True, "Transaccion y orden no procesadas"

    finally:
        db.close()



# ==========================================
# 3. VERIFICACION CON PAYMENT SERVICE
# ==========================================

def verify_payment(transaction_id, order_id):
    """Verifica que el pago exista y este confirmado."""

    internal_key = os.getenv("INTERNAL_SERVICE_KEY")

    if not internal_key:
        return False, "INTERNAL_SERVICE_KEY no configurada"

    payment_service_url = os.getenv(
        "PAYMENT_SERVICE_URL",
        "http://payment-service:8000"
    ).rstrip("/")

    safe_transaction_id = urllib.parse.quote(
        transaction_id,
        safe=""
    )

    url = (
        f"{payment_service_url}"
        f"/payments/internal/transactions/{safe_transaction_id}"
    )

    request = urllib.request.Request(
        url,
        headers={
            "X-Internal-Service-Key": internal_key
        },
        method="GET"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=10
        ) as response:
            payment = json.load(response)

    except urllib.error.HTTPError as exc:
        return False, f"Payment Service respondio HTTP {exc.code}"

    except (urllib.error.URLError, TimeoutError) as exc:
        return False, f"No se pudo consultar Payment Service: {exc}"

    except (ValueError, TypeError):
        return False, "Respuesta JSON invalida de Payment Service"

    if not isinstance(payment, dict):
        return False, "Respuesta de pago invalida"

    if payment.get("transaction_id") != transaction_id:
        return False, "La transaccion no coincide"

    returned_order_id = payment.get("order_id")

    if (
        type(returned_order_id) is not int
        or returned_order_id != order_id
    ):
        return False, "La orden no coincide"

    if payment.get("status") != "PAID":
        return False, "El pago no esta confirmado"

    payment_user_id = payment.get("user_id")

    if type(payment_user_id) is not int or payment_user_id <= 0:
        return False, "Usuario del pago invalido"

    return True, {
        "message": "Pago confirmado en Payment Service",
        "user_id": payment_user_id
    }


# ==========================================
# 4. VERIFICACION CON ORDER SERVICE
# ==========================================

def verify_order(order_id, event_items):
    """Comprueba que los productos coincidan con la orden."""

    internal_key = os.getenv("INTERNAL_SERVICE_KEY")

    if not internal_key:
        return False, "INTERNAL_SERVICE_KEY no configurada"

    order_service_url = os.getenv(
        "ORDER_SERVICE_URL",
        "http://order-service:8000"
    ).rstrip("/")

    url = f"{order_service_url}/orders/internal/{order_id}"

    request = urllib.request.Request(
        url,
        headers={
            "X-Internal-Service-Key": internal_key
        },
        method="GET"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=10
        ) as response:
            order = json.load(response)

    except urllib.error.HTTPError as exc:
        return False, f"Order Service respondio HTTP {exc.code}"

    except (urllib.error.URLError, TimeoutError) as exc:
        return False, f"No se pudo consultar Order Service: {exc}"

    except (ValueError, TypeError):
        return False, "Respuesta JSON invalida de Order Service"

    if not isinstance(order, dict):
        return False, "Respuesta de orden invalida"

    if (
        type(order.get("order_id")) is not int
        or order["order_id"] != order_id
    ):
        return False, "El identificador de orden no coincide"

    if order.get("status") != "PAID":
        return False, "La orden no esta pagada"

    order_items = order.get("items")

    if not isinstance(order_items, list) or not order_items:
        return False, "La orden no contiene productos validos"

    def normalize_items(items):
        """Agrupa cantidades por identificador de producto."""

        normalized = {}

        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Item invalido")

            product_id = item.get("product_id")
            quantity = item.get("quantity")

            if type(product_id) is not int or product_id <= 0:
                raise ValueError("Producto invalido")

            if type(quantity) is not int or quantity <= 0:
                raise ValueError("Cantidad invalida")

            normalized[product_id] = (
                normalized.get(product_id, 0) + quantity
            )

        return normalized

    try:
        expected = normalize_items(order_items)
        received = normalize_items(event_items)

    except (ValueError, TypeError):
        return False, "Productos o cantidades invalidos"

    if expected != received:
        return False, "Los productos o cantidades no coinciden"

    order_user_id = order.get("user_id")

    if type(order_user_id) is not int or order_user_id <= 0:
        return False, "Usuario de la orden invalido"

    return True, {
        "message": "Productos y cantidades verificados",
        "user_id": order_user_id
    }


# ==========================================
# 5. INSPECCION SEGURA DE LA DLQ
# ==========================================


def inspect_for_retry(retry=False):
    """
    Inspecciona un mensaje de la DLQ.

    Por defecto, solo realiza un dry-run.
    Con retry=True, publica un mensaje validado
    y confirma el original despues del publish.
    """

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            heartbeat=60,
            blocked_connection_timeout=30
        )
    )

    channel = connection.channel()
    method = None
    settled = False

    try:
        method, properties, body = channel.basic_get(
            queue=DLQ_NAME,
            auto_ack=False
        )

        if method is None:
            print("La DLQ esta vacia")
            return

        print("\n===================================")
        print(
            "RECUPERACION DLQ - "
            + ("MODO RETRY" if retry else "MODO DRY-RUN")
        )
        print("===================================")

        # PASO 1: Decodificar JSON
        try:
            message = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print("ERROR: el mensaje no contiene JSON valido")
            print("DECISION: NO RECUPERABLE AUTOMATICAMENTE")
            return

        print(json.dumps(
            message,
            indent=4,
            ensure_ascii=False
        ))

        # PASO 2: Validar estructura
        valid, reason = validate_event(message)

        print("\nVALIDACION:")
        print("Resultado:", reason)

        if not valid:
            print("DECISION: NO RECUPERABLE AUTOMATICAMENTE")
            return

        # PASO 3: Verificar idempotencia
        can_retry, reason = check_processed(
            message["transaction_id"],
            message["order_id"]
        )

        print("\nIDEMPOTENCIA:")
        print("Resultado:", reason)

        if not can_retry:
            print("DECISION: NO REENVIAR")
            return

        # PASO 4: Verificar pago
        print("\nVERIFICACION PAYMENT SERVICE:")

        payment_verified, payment_result = verify_payment(
            message["transaction_id"],
            message["order_id"]
        )

        if not payment_verified:
            print("Resultado:", payment_result)
            print("DECISION: NO AUTORIZADO PARA REENVIO")
            return

        print("Resultado:", payment_result["message"])

        # PASO 5: Verificar orden
        print("\nVERIFICACION ORDER SERVICE:")

        order_verified, order_result = verify_order(
            message["order_id"],
            message["items"]
        )

        if not order_verified:
            print("Resultado:", order_result)
            print("DECISION: NO AUTORIZADO PARA REENVIO")
            return

        print("Resultado:", order_result["message"])

        # PASO 6: Verificar propietario
        payment_user_id = payment_result["user_id"]
        order_user_id = order_result["user_id"]

        print("\nVERIFICACION DEL PROPIETARIO:")
        print("Usuario del pago:", payment_user_id)
        print("Usuario de la orden:", order_user_id)

        if payment_user_id != order_user_id:
            print("DECISION: PROPIETARIOS NO COINCIDEN")
            return

        print("Resultado: propietarios coinciden")

        # PASO 7: Decision final
        print("\nDECISION:")
        print("PAGO, ORDEN, PRODUCTOS Y PROPIETARIO VERIFICADOS")

        if not retry:
            print("DRY-RUN: no se reenviara ningun mensaje")
            return

        # PASO 8: Publicar con confirmacion
        print("\nPUBLICACION CONTROLADA:")

        channel.confirm_delivery()

        publish_with_confirmation(channel, body)

        print("RabbitMQ confirmo la publicacion")

        # PASO 9: Confirmar el mensaje original
        channel.basic_ack(
            delivery_tag=method.delivery_tag
        )

        settled = True

        print("ACK enviado para el mensaje original")
        print("RECUPERACION: PUBLICACION CONFIRMADA")

    finally:
        try:
            if method is not None and not settled and channel.is_open:
                channel.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=True
                )
                settled = True
        finally:
            if connection.is_open:
                connection.close()

        if method is not None and not retry and settled:
            print("\nMensaje conservado en la DLQ")
        elif method is not None and retry and not settled:
            print(
                "\nNo se pudo confirmar el estado final "
                "del mensaje original"
            )

MAIN_QUEUE_NAME = "product_payment_completed"



def publish_with_confirmation(channel, body):
    """
    Publica un mensaje persistente.

    El canal debe tener publisher confirms
    habilitados antes de llamar esta funcion.

    En Pika BlockingChannel, una publicacion
    confirmada normalmente devuelve None.
    """

    channel.queue_declare(
        queue=MAIN_QUEUE_NAME,
        passive=True
    )

    try:
        channel.basic_publish(
            exchange="",
            routing_key=MAIN_QUEUE_NAME,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2
            ),
            mandatory=True
        )

    except pika.exceptions.UnroutableError as exc:
        raise RuntimeError(
            "RabbitMQ no pudo enrutar el mensaje"
        ) from exc

    except pika.exceptions.NackError as exc:
        raise RuntimeError(
            "RabbitMQ rechazo la publicacion"
        ) from exc

    return True




# ==========================================
# EJECUCION PRINCIPAL
# ==========================================


if __name__ == "__main__":
    try:
        if len(sys.argv) == 1:
            inspect_for_retry(retry=False)

        elif sys.argv[1:] == ["--retry"]:
            inspect_for_retry(retry=True)

        else:
            print(
                "Uso: python -m scripts.retry_dlq [--retry]",
                file=sys.stderr
            )
            sys.exit(2)

    except Exception as exc:
        print(
            f"Error durante recuperacion: {exc}",
            file=sys.stderr
        )
        sys.exit(1)

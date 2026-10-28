
import json
import os
import urllib.error
import urllib.parse
import urllib.request



def internal_get(base_url, path):
    """Consulta un endpoint interno protegido."""

    internal_key = os.getenv("INTERNAL_SERVICE_KEY")

    if not internal_key:
        raise TemporaryValidationError(
            "INTERNAL_SERVICE_KEY no configurada"
        )

    url = base_url.rstrip("/") + path

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
            data = json.load(response)

    except urllib.error.HTTPError as exc:

        if exc.code in (408, 429, 500, 502, 503, 504):
            raise TemporaryValidationError(
                f"Servicio temporalmente no disponible: HTTP {exc.code}"
            ) from exc

        if exc.code in (401, 403):
            raise TemporaryValidationError(
                f"Error de autenticacion interna: HTTP {exc.code}"
            ) from exc

        if exc.code == 404:
            raise PermanentValidationError(
                "Recurso interno no encontrado: HTTP 404"
            ) from exc

        raise TemporaryValidationError(
            f"Respuesta HTTP inesperada: {exc.code}"
        ) from exc

    except (urllib.error.URLError, TimeoutError) as exc:
        raise TemporaryValidationError(
            f"No se pudo consultar el servicio: {exc}"
        ) from exc

    except (ValueError, TypeError) as exc:
        raise TemporaryValidationError(
            "Respuesta JSON invalida del servicio interno"
        ) from exc

    if not isinstance(data, dict):
        raise TemporaryValidationError(
            "Respuesta del servicio interno invalida"
        )

    return True, data



def normalize_items(items):
    """Agrupa productos repetidos y suma cantidades."""

    if not isinstance(items, list) or not items:
        raise ValueError("Lista de productos invalida")

    normalized = {}

    for item in items:

        if not isinstance(item, dict):
            raise ValueError("Item invalido")

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if type(product_id) is not int or product_id <= 0:
            raise ValueError("product_id invalido")

        if type(quantity) is not int or quantity <= 0:
            raise ValueError("quantity invalida")

        normalized[product_id] = (
            normalized.get(product_id, 0) + quantity
        )

    return normalized


def verify_payment(transaction_id, order_id):
    """Verifica un pago confirmado y su propietario."""

    if (
        not isinstance(transaction_id, str)
        or not transaction_id.strip()
        or type(order_id) is not int
        or order_id <= 0
    ):
        return False, "Datos de pago invalidos"

    base_url = os.getenv(
        "PAYMENT_SERVICE_URL",
        "http://payment-service:8000"
    )

    safe_transaction_id = urllib.parse.quote(
        transaction_id,
        safe=""
    )

    ok, result = internal_get(
        base_url,
        f"/payments/internal/transactions/{safe_transaction_id}"
    )

    if not ok:
        return False, result

    if result.get("transaction_id") != transaction_id:
        return False, "La transaccion no coincide"

    if (
        type(result.get("order_id")) is not int
        or result["order_id"] != order_id
    ):
        return False, "La orden del pago no coincide"

    if result.get("status") != "PAID":
        return False, "El pago no esta confirmado"

    user_id = result.get("user_id")

    if type(user_id) is not int or user_id <= 0:
        return False, "Usuario del pago invalido"

    return True, {
        "message": "Pago confirmado",
        "user_id": user_id,
        "inventory_reservation_id": result.get("inventory_reservation_id"),
    }


def verify_order(order_id, event_items):
    """Verifica la orden, su propietario y productos."""

    if type(order_id) is not int or order_id <= 0:
        return False, "order_id invalido"

    try:
        received = normalize_items(event_items)
    except ValueError as exc:
        return False, str(exc)

    base_url = os.getenv(
        "ORDER_SERVICE_URL",
        "http://order-service:8000"
    )

    ok, result = internal_get(
        base_url,
        f"/orders/internal/{order_id}"
    )

    if not ok:
        return False, result

    if (
        type(result.get("order_id")) is not int
        or result["order_id"] != order_id
    ):
        return False, "La orden no coincide"

    # Ambos consumidores reciben el pago independientemente. No exigir
    # que Order haya procesado primero el mismo evento.
    # Un pago PAID ya verificado impide completar una cancelacion concurrente.
    if result.get("status") not in ("PENDING", "CANCELLING", "PAID", "PROCESSING", "SHIPPED", "DELIVERED"):
        return False, "La orden no permite procesar este pago"

    try:
        expected = normalize_items(result.get("items"))
    except ValueError as exc:
        return False, f"Productos de la orden invalidos: {exc}"

    if expected != received:
        return False, "Productos o cantidades no coinciden"

    user_id = result.get("user_id")

    if type(user_id) is not int or user_id <= 0:
        return False, "Usuario de la orden invalido"

    return True, {
        "message": "Orden y productos verificados",
        "user_id": user_id
    }


def verify_payment_and_order(message):
    """
    Verifica pago, orden, productos y propietario.
    No modifica la base de datos ni RabbitMQ.
    """

    if not isinstance(message, dict):
        return False, "Evento invalido"

    if message.get("event") != "PAYMENT_COMPLETED":
        return False, "Tipo de evento incorrecto"

    order_id = message.get("order_id")
    transaction_id = message.get("transaction_id")
    items = message.get("items")

    payment_ok, payment = verify_payment(
        transaction_id,
        order_id
    )

    if not payment_ok:
        return False, f"Pago rechazado: {payment}"

    if message.get("inventory_reservation_id") != payment.get("inventory_reservation_id"):
        return False, "La reserva no coincide con el pago confirmado"

    order_ok, order = verify_order(
        order_id,
        items
    )

    if not order_ok:
        return False, f"Orden rechazada: {order}"

    if payment["user_id"] != order["user_id"]:
        return False, "El propietario del pago no coincide con la orden"

    return True, "Pago, orden, productos y propietario verificados"


class PermanentValidationError(Exception):
    """El evento contiene datos invalidos o inconsistentes."""


class TemporaryValidationError(Exception):
    """No fue posible verificar el evento temporalmente."""

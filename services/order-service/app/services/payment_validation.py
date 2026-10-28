import json
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

from app.core.config import settings


class PermanentValidationError(Exception):
    """Evento invalido o inconsistente."""


class TemporaryValidationError(Exception):
    """No se pudo verificar el pago temporalmente."""


def verify_payment_event(message: dict, order) -> None:
    """
    Verifica que un evento PAYMENT_COMPLETED corresponda
    a una transaccion confirmada en Payment Service.

    No modifica PostgreSQL ni RabbitMQ.
    """

    if not isinstance(message, dict):
        raise PermanentValidationError(
            "El evento debe ser un objeto JSON"
        )

    if message.get("event") != "PAYMENT_COMPLETED":
        raise PermanentValidationError(
            "Tipo de evento incorrecto"
        )

    order_id = message.get("order_id")
    user_id = message.get("user_id")
    transaction_id = message.get("transaction_id")
    amount = message.get("amount")

    if type(order_id) is not int or order_id <= 0:
        raise PermanentValidationError("order_id invalido")

    if type(user_id) is not int or user_id <= 0:
        raise PermanentValidationError("user_id invalido")

    if (
        not isinstance(transaction_id, str)
        or not transaction_id.strip()
    ):
        raise PermanentValidationError(
            "transaction_id invalido"
        )

    if order.id != order_id:
        raise PermanentValidationError(
            "La orden del evento no coincide"
        )

    if order.user_id != user_id:
        raise PermanentValidationError(
            "El usuario del evento no coincide"
        )

    try:
        event_amount = Decimal(str(amount))
        order_amount = Decimal(str(order.total))

        if (
            not event_amount.is_finite()
            or event_amount <= 0
            or event_amount != order_amount
        ):
            raise PermanentValidationError(
                "El importe del evento no coincide con la orden"
            )

    except (InvalidOperation, TypeError, ValueError):
        raise PermanentValidationError(
            "Importe del evento invalido"
        )

    safe_transaction_id = urllib.parse.quote(
        transaction_id,
        safe=""
    )

    url = (
        settings.PAYMENT_SERVICE_URL.rstrip("/")
        + "/payments/internal/transactions/"
        + safe_transaction_id
    )

    request = urllib.request.Request(
        url,
        headers={
            "X-Internal-Service-Key":
                settings.INTERNAL_SERVICE_KEY
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
        if exc.code == 404:
            raise PermanentValidationError(
                "Transaccion no encontrada"
            ) from exc

        raise TemporaryValidationError(
            f"Error consultando Payment Service: HTTP {exc.code}"
        ) from exc

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError
    ) as exc:
        raise TemporaryValidationError(
            "Payment Service no disponible"
        ) from exc

    except (ValueError, TypeError) as exc:
        raise TemporaryValidationError(
            "Respuesta invalida de Payment Service"
        ) from exc

    if not isinstance(payment, dict):
        raise TemporaryValidationError(
            "Payment Service devolvio datos invalidos"
        )

    if payment.get("transaction_id") != transaction_id:
        raise PermanentValidationError(
            "La transaccion consultada no coincide"
        )

    if (
        type(payment.get("order_id")) is not int
        or payment["order_id"] != order_id
    ):
        raise PermanentValidationError(
            "La transaccion pertenece a otra orden"
        )

    if (
        type(payment.get("user_id")) is not int
        or payment["user_id"] != user_id
    ):
        raise PermanentValidationError(
            "La transaccion pertenece a otro usuario"
        )

    if payment.get("status") != "PAID":
        raise PermanentValidationError(
            "La transaccion no esta confirmada"
        )

    try:
        payment_amount = Decimal(str(payment.get("amount")))

        if (
            not payment_amount.is_finite()
            or payment_amount != order_amount
        ):
            raise PermanentValidationError(
                "El importe pagado no coincide con la orden"
            )

    except (InvalidOperation, TypeError, ValueError):
        raise TemporaryValidationError(
            "Payment Service devolvio un importe invalido"
        )
from fastapi import APIRouter

from app.schemas import PaymentNotification, NotificationCreate, NotificationResponse


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)


@router.get("/health")
def notification_health():

    return {
        "service": "Notification Service",
        "status": "healthy"
    }


@router.post("/payment")
def payment_notification(
    notification: PaymentNotification
):

    print("")
    print("================================")
    print("       NOTIFICACIÓN DE PAGO")
    print("================================")
    print(f"Usuario: {notification.user_email}")
    print(f"Orden: #{notification.order_id}")
    print(f"Monto: ${notification.amount}")
    print(f"Estado: {notification.status}")
    print(f"Transacción: {notification.transaction_id}")
    print("Mensaje: Pago realizado correctamente.")
    print("================================")
    print("")

    return {
        "message": "Notificación procesada correctamente",
        "order_id": notification.order_id,
        "status": notification.status
    }

@router.post(
    "",
    response_model=NotificationResponse
)
def send_notification(
    notification: NotificationCreate
):

    print("=================================")
    print("      NOTIFICACIÓN ENVIADA")
    print("=================================")
    print(f"Usuario: {notification.user_id}")
    print(f"Email: {notification.email}")
    print(f"Asunto: {notification.subject}")
    print(f"Mensaje: {notification.message}")
    print("=================================")

    return {
        "status": "SENT",
        "user_id": notification.user_id,
        "email": notification.email,
        "subject": notification.subject,
        "message": notification.message
    }
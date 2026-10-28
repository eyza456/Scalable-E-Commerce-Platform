from decimal import Decimal

from pydantic import BaseModel


class PaymentNotification(BaseModel):

    user_id: int

    user_email: str

    order_id: int

    amount: Decimal

    transaction_id: str

    status: str


from pydantic import BaseModel


class NotificationCreate(BaseModel):

    user_id: int

    email: str

    subject: str

    message: str


class NotificationResponse(BaseModel):

    status: str

    user_id: int

    email: str

    subject: str

    message: str
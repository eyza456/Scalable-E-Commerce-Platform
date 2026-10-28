from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class OrderItemResponse(BaseModel):

    product_id: int

    product_name: str

    quantity: int

    price: Decimal

    subtotal: Decimal

    model_config = ConfigDict(
        from_attributes=True
    )


class OrderResponse(BaseModel):
    checkout_id: str | None = None

    id: int

    user_id: int

    status: str

    total: Decimal

    created_at: datetime

    items: list[OrderItemResponse]

    model_config = ConfigDict(
        from_attributes=True
    )


class CheckoutPendingResponse(BaseModel):
    checkout_id: str
    checkout_status: Literal["PENDING"] = "PENDING"


class OrderStatusUpdate(BaseModel):

    status: Literal[
        "PROCESSING",
        "SHIPPED",
        "DELIVERED"
    ]


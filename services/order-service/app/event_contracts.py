"""Contratos de eventos publicados por Payment Service."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PaymentItemContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: int = Field(strict=True, gt=0)
    quantity: int = Field(strict=True, gt=0)


class PaymentCompletedEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event: Literal["PAYMENT_COMPLETED"]
    order_id: int = Field(strict=True, gt=0)
    user_id: int = Field(strict=True, gt=0)
    transaction_id: str = Field(min_length=1)
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    items: list[PaymentItemContract] = Field(min_length=1)
    inventory_reservation_id: str | None = Field(default=None, min_length=1)

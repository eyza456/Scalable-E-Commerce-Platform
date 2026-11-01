"""Contrato minimo y estricto del evento de inventario."""

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
    user_id: int | None = Field(default=None, strict=True, gt=0)
    transaction_id: str = Field(min_length=1)
    items: list[PaymentItemContract] = Field(min_length=1)
    inventory_reservation_id: str | None = Field(default=None, min_length=1)

"""Contratos estrictos para la coordinacion de cancelaciones."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CancellationDone(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: int = Field(strict=True, gt=0)
    user_id: int = Field(strict=True, gt=0)
    status: Literal["DONE"]


class PaymentConfirmedDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: Literal["PAYMENT_CONFIRMED"]
    order_id: int = Field(strict=True, gt=0)

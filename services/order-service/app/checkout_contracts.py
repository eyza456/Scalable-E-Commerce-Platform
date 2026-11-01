"""Versioned wire contracts consumed by checkout."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from typing import Optional


class CartItemContract(BaseModel):
    product_id: int = Field(strict=True, gt=0)
    quantity: int = Field(strict=True, ge=1, le=100)
    price: Decimal = Field(gt=0, allow_inf_nan=False)


class CartSnapshotContract(BaseModel):
    user_id: int = Field(strict=True, gt=0)
    version: str = Field(min_length=1)
    checkout_id: Optional[str] = Field(default=None, min_length=1)
    items: list[CartItemContract] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def unique_products(cls, value):
        ids = [item.product_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("items repetidos")
        return value


class ProductContract(BaseModel):
    id: int = Field(strict=True, gt=0)
    name: str = Field(min_length=1)
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    stock: int = Field(strict=True, ge=0)
    is_active: StrictBool


class CartActionContract(BaseModel):
    checkout_id: str = Field(min_length=1)
    state: str = Field(pattern="^(PREPARED|COMMITTED|ABORTED)$")

    model_config = ConfigDict(extra="ignore")


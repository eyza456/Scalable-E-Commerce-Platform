from decimal import Decimal

from pydantic import BaseModel, Field


class CartItemCreate(BaseModel):

    product_id: int = Field(
        gt=0
    )

    quantity: int = Field(
        gt=0,
        le=100
    )


class CartItemResponse(BaseModel):

    product_id: int

    name: str

    quantity: int

    price: Decimal

    subtotal: Decimal


class CartResponse(BaseModel):

    user_id: int

    items: list[CartItemResponse]

    total: Decimal


class CartItemUpdate(BaseModel):

    quantity: int = Field(
        gt=0,
        le=100
    )
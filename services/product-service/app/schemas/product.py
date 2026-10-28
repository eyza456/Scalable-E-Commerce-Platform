from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductCreate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def category_choice(self):
        if "category" in self.model_fields_set and "category_id" in self.model_fields_set:
            raise ValueError("Enviar category_id o category, no ambos")
        return self
    name: str = Field(
        min_length=2,
        max_length=150
    )

    description: str | None = Field(
        default=None,
        max_length=2000
    )

    price: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2
    )

    stock: int = Field(
        ge=0
    )

    category: str | None = Field(
        default=None,
        max_length=100
    )

    image_url: str | None = Field(
        default=None,
        max_length=500
    )


class ProductUpdate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_update(self):
        if "category" in self.model_fields_set and "category_id" in self.model_fields_set:
            raise ValueError("Enviar category_id o category, no ambos")
        for field in ("name", "price", "stock", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} no puede ser null")
        return self
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=150
    )

    description: str | None = Field(
        default=None,
        max_length=2000
    )

    price: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2
    )

    stock: int | None = Field(
        default=None,
        ge=0
    )

    category: str | None = Field(
        default=None,
        max_length=100
    )

    image_url: str | None = Field(
        default=None,
        max_length=500
    )

    is_active: bool | None = None


class ProductResponse(BaseModel):
    category_id: int | None
    id: int
    name: str
    description: str | None
    price: Decimal
    stock: int
    category: str | None
    image_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True
    )

class StockDecrease(BaseModel):
    quantity: int = Field(
        gt=0
    )

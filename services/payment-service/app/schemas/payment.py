from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):

    order_id: int = Field(
        gt=0
    )

    method: str = Field(
        min_length=3,
        max_length=50
    )


class PaymentResponse(BaseModel):
    processed_at: datetime | None = None

    id: int
    order_id: int
    user_id: int
    amount: float
    method: str
    status: str
    transaction_id: str | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )

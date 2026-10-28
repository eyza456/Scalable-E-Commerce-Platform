from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class CategoryResponse(CategoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime

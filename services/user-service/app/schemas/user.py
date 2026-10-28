from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class UserCreate(BaseModel):
    name: str = Field(
        min_length=3,
        max_length=100
    )

    email: EmailStr 

    password: str = Field(
        min_length=6,
        max_length=100
    )

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int 
    name: str
    email: EmailStr
    role: str
    is_active: bool
    create_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )

class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=3, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def valid_changes(self):
        if not self.model_fields_set:
            raise ValueError("Enviar al menos name o email")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Los campos de perfil no pueden ser null")
        return self


class UserUpdateResponse(UserResponse):
    access_token: str
    token_type: str = "bearer"

    



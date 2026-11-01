from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator, field_validator


def bcrypt_input(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("La contrasena admite un maximo de 72 bytes UTF-8")
    return value


class UserCreate(BaseModel):
    name: str = Field(
        min_length=3,
        max_length=100
    )

    email: EmailStr = Field(max_length=254)

    password: str = Field(
        min_length=6,
        max_length=72
    )

    _password_bytes = field_validator("password")(bcrypt_input)

class UserLogin(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(max_length=72)
    _password_bytes = field_validator("password")(bcrypt_input)

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
    email: EmailStr | None = Field(default=None, max_length=254)

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


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["Customer", "seller", "admin"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def valid_changes(self):
        if not self.model_fields_set:
            raise ValueError("Enviar al menos role o is_active")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Los campos administrativos no pueden ser null")
        return self

    



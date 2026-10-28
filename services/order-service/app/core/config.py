from http.client import PAYMENT_REQUIRED
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    DATABASE_URL: str

    SECRET_KEY: str

    JWT_ALGORITHM: str = "HS256"

    CART_SERVICE_URL: str = "http://cart-service:8000"

    PRODUCT_SERVICE_URL: str = "http://product-service:8000"

    INTERNAL_SERVICE_KEY: str

    PAYMENT_SERVICE_URL: str = "http://payment-service:8000"


settings = Settings()

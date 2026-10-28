from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    REDIS_HOST: str = "redis"

    REDIS_PORT: int = 6379

    SECRET_KEY: str

    JWT_ALGORITHM: str = "HS256"

    PRODUCT_SERVICE_URL: str = "http://product-service:8000"


settings = Settings()
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    DATABASE_URL: str

    SECRET_KEY: str
    JWT_ALGORITHM: str

    ORDER_SERVICE_URL: str
    PRODUCT_SERVICE_URL: str
    INTERNAL_SERVICE_KEY: str
    

    class Config:
        env_file = ".env"


settings = Settings()
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str

    SECRET_KEY: str
    JWT_ALGORITHM: str

    class Config:
        case_sensitive = True


settings = Settings()
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: str = "dev-secret-key"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/payments"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    outbox_poll_interval_seconds: int = 1

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

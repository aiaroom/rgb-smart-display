from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


class ApplicationSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    name: str = "rgb-smart-display"
    environment: Environment = Environment.LOCAL
    debug: bool = True


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    host: str
    port: int = 5432
    user: str
    password: str
    database: str

    echo: bool = False
    pool_pre_ping: bool = True
    pool_size: int = 10
    max_overflow: int = 5

    @property
    def async_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )

    @property
    def sync_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    secret_key: str = "0123456789"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7


class UjinSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    base_url: str = ""
    local_url: str = ""
    token: str = ""
    email: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app: ApplicationSettings = ApplicationSettings()
    pg: PostgresSettings
    auth: AuthSettings = AuthSettings()
    ujin: UjinSettings = UjinSettings()


settings = Settings()
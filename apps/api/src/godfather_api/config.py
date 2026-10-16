"""Explicit environment configuration; secrets never appear in settings reprs."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GODFATHER_", extra="ignore", hide_input_in_errors=True
    )

    environment: Literal["local", "test"] = "local"
    database_host: str = Field(default="postgres", min_length=1)
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(default="godfather", pattern=r"^[a-z][a-z0-9_]{0,62}$")
    database_user: str = Field(default="godfather", min_length=1)
    database_password: SecretStr
    database_timeout_seconds: int = Field(default=3, ge=1, le=30)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_password")
    @classmethod
    def nonempty_password(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("database password must not be blank")
        return value

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )

"""Explicit environment configuration; secrets never appear in settings reprs."""

import re
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GODFATHER_", extra="ignore", hide_input_in_errors=True
    )

    environment: Literal["local", "test", "production"] = "local"
    database_host: str = Field(default="postgres", min_length=1)
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(default="godfather", pattern=r"^[a-z][a-z0-9_]{0,62}$")
    database_user: str = Field(default="godfather", min_length=1)
    database_password: SecretStr
    database_timeout_seconds: int = Field(default=3, ge=1, le=30)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    heartbeat_interval_seconds: int = Field(default=10, ge=1, le=300)
    suspect_after_seconds: int = Field(default=20, ge=2, le=1800)
    offline_after_seconds: int = Field(default=30, ge=3, le=3600)
    health_scan_seconds: int = Field(default=1, ge=1, le=60)
    health_monitor_enabled: bool = True
    scheduler_enabled: bool = True
    execution_lease_seconds: int = Field(default=30, ge=3, le=3600)
    artifact_directory: Path = Path(".cache/artifacts")
    web_origin: str = "http://127.0.0.1:3000"
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    # Optional legacy subject pin; normal founder setup only needs the email allowlist.
    google_bootstrap_subject: str = Field(default="", max_length=255, repr=False)
    google_bootstrap_email: str = Field(default="", max_length=320, repr=False)
    session_seconds: int = Field(default=28800, ge=300, le=86400)
    authentication_limit: int = Field(default=20, ge=1, le=100)
    # Legacy credentials are accepted ONLY in explicitly isolated regression tests.
    test_legacy_credentials: bool = False

    @field_validator("google_bootstrap_email")
    @classmethod
    def founder_email(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Configure one exact founder Google email address or leave it blank")
        return value

    @field_validator("web_origin")
    @classmethod
    def trusted_web_origin(cls, value: str) -> str:
        from urllib.parse import urlsplit

        url = urlsplit(value)
        local = url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1")
        production = value == "https://app.the-godfather.ai"
        if (
            not (local or production)
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Configure an exact loopback origin or the planned HTTPS Command Center origin"
            )
        return value

    @property
    def google_redirect_uri(self) -> str:
        return self.web_origin + "/api/auth/callback"

    @model_validator(mode="after")
    def health_thresholds(self) -> "Settings":
        if self.environment == "test" and self.database_name != "godfather_test":
            raise ValueError("Test authentication requires the isolated godfather_test database")
        if self.environment == "production" and (
            self.web_origin != "https://app.the-godfather.ai"
            or not self.google_client_id
            or not self.google_client_secret.get_secret_value()
            or self.test_legacy_credentials
        ):
            raise ValueError(
                "Production requires HTTPS, configured Google OIDC, and no legacy test credentials"
            )
        if not (
            self.heartbeat_interval_seconds
            < self.suspect_after_seconds
            < self.offline_after_seconds
        ):
            raise ValueError("heartbeat interval must be less than suspect and offline thresholds")
        return self

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

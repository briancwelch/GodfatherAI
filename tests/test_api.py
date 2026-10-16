"""API behavior and logs without any live database requirement."""

import json
import logging
from collections.abc import Iterator
from io import StringIO
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.logging import JsonFormatter, correlation_id
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import OperationalError


@pytest.fixture
def logs() -> StringIO:
    return StringIO()


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, logs: StringIO) -> Iterator[tuple[TestClient, Mock]]:
    database = Mock(spec=Database)
    database.ready.return_value = True
    monkeypatch.setattr("godfather_api.app.Database", lambda _: database)
    app = create_app(
        Settings(database_password=SecretStr("unit-secret"), health_monitor_enabled=False)
    )
    handler = logging.getLogger("godfather").handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(logs)
    with TestClient(app) as client:
        yield client, database
    database.close.assert_called_once()


def test_configuration_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GODFATHER_DATABASE_PASSWORD", raising=False)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_port": 0},
        {"database_port": 65536},
        {"database_timeout_seconds": 0},
        {"database_password": "  "},
        {"database_name": "not/a/database"},
        {"environment": "production"},
        {"log_level": "invalid"},
    ],
)
def test_configuration_rejects_invalid_values(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {"database_password": "unit-secret", **overrides}
    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_password_is_hidden_and_url_is_escaped() -> None:
    secret = "secret:@/with?special#characters"
    settings = Settings(database_password=SecretStr(secret))
    assert secret not in repr(settings)
    assert secret not in str(settings.database_url)
    assert settings.database_url.password == secret
    assert settings.database_url.drivername == "postgresql+psycopg"


def test_api_version_and_health_contract(api: tuple[TestClient, Mock]) -> None:
    client, database = api
    assert client.get("/api/v1").json() == {"service": "the-godfather", "api_version": "v1"}
    assert client.get("/health/live").json() == {"status": "alive"}
    database.ready.assert_not_called()
    assert client.get("/health/ready").json() == {"status": "ready"}
    assert client.get("/docs").status_code == 404
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert {"/api/v1", "/health/live", "/health/ready"} <= set(paths)
    assert "/api/v1/workers/register" in paths


def test_readiness_refuses_unmigrated_schema(api: tuple[TestClient, Mock]) -> None:
    client, database = api
    database.ready.return_value = False
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert client.get("/health/live").status_code == 200


def test_database_failure_is_redacted(api: tuple[TestClient, Mock], logs: StringIO) -> None:
    client, database = api
    database.ready.side_effect = OperationalError("private SQL", {}, Exception("db-password"))
    response = client.get("/health/ready")
    assert response.status_code == 503
    output = logs.getvalue()
    assert "db-password" not in output + response.text
    assert "private SQL" not in output + response.text
    events = [json.loads(line) for line in output.splitlines()]
    assert any(row["event"] == "database.unavailable" for row in events)


@pytest.mark.parametrize("value", ["", "a" * 65, "bad/id", "bad id"])
def test_invalid_correlation_id_is_replaced(api: tuple[TestClient, Mock], value: str) -> None:
    response = api[0].get("/health/live", headers={"X-Correlation-ID": value})
    assert len(response.headers["X-Correlation-ID"]) == 32
    assert response.headers["X-Correlation-ID"] != value


def test_correlation_is_returned_logged_and_reset(
    api: tuple[TestClient, Mock], logs: StringIO
) -> None:
    client, _ = api
    response = client.get(
        "/health/live?token=private-query",
        headers={
            "X-Correlation-ID": "request-123",
            "Authorization": "Bearer private-token",
        },
    )
    assert response.headers["X-Correlation-ID"] == "request-123"
    output = logs.getvalue()
    assert "private-query" not in output
    assert "private-token" not in output
    rows = [json.loads(line) for line in output.splitlines()]
    assert rows[-1]["correlation_id"] == "request-123"
    assert rows[-1]["route"] == "/health/live"
    assert correlation_id.get() is None
    assert client.get("/health/live").headers["X-Correlation-ID"] != "request-123"


def test_duplicate_id_and_unknown_path_are_safe(
    api: tuple[TestClient, Mock], logs: StringIO
) -> None:
    response = api[0].get(
        "/private-path", headers=[("x-correlation-id", "a"), ("x-correlation-id", "b")]
    )
    assert response.status_code == 404
    assert len(response.headers["X-Correlation-ID"]) == 32
    assert "private-path" not in logs.getvalue()


def test_unexpected_failure_returns_safe_error(
    api: tuple[TestClient, Mock], logs: StringIO
) -> None:
    client, database = api
    database.ready.side_effect = RuntimeError("private-exception")
    response = client.get("/health/ready")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["X-Correlation-ID"]
    assert "private-exception" not in logs.getvalue()


def test_json_formatter_does_not_serialize_exception_or_extra_secrets() -> None:
    record = logging.makeLogRecord(
        {
            "name": "godfather.test",
            "levelname": "ERROR",
            "msg": "safe.event",
            "password": "private-password",
            "exc_info": (RuntimeError, RuntimeError("secret"), None),
        }
    )
    serialized = JsonFormatter().format(record)
    assert "private-password" not in serialized
    assert "secret" not in serialized
    assert json.loads(serialized)["event"] == "safe.event"

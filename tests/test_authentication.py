"""Authentication configuration and cookie guarantees without a database."""

import pytest
from fastapi.responses import JSONResponse
from godfather_api.authentication import cookie
from godfather_api.config import Settings
from pydantic import ValidationError


def test_production_session_is_secure_httponly_and_host_only() -> None:
    settings = Settings(
        database_password="test",
        environment="production",
        test_legacy_credentials=False,
        web_origin="https://app.the-godfather.ai",
        google_client_id="test",
        google_client_secret="test",
    )
    response = JSONResponse({})
    cookie(response, "godfather_session", "test-only-session", settings, 300)
    value = response.headers["set-cookie"]
    assert "Secure" in value and "HttpOnly" in value and "SameSite=strict" in value
    assert "Domain=" not in value and "Max-Age=300" in value


@pytest.mark.parametrize(
    "origin",
    [
        "https://attacker.invalid",
        "http://127.0.0.1:3000/path",
        "http://user@127.0.0.1:3000",
        "https://app.the-godfather.ai.attacker.invalid",
        "http://127.0.0.1:3000?next=evil",
    ],
)
def test_only_exact_reviewed_origins_are_configurable(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_password="test", web_origin=origin)


def test_test_authentication_cannot_target_application_database() -> None:
    with pytest.raises(ValidationError):
        Settings(database_password="test", environment="test", database_name="godfather")

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
        "http://attacker.invalid",
        "http://127.0.0.1:3000/path",
        "http://user@127.0.0.1:3000",
        "https://user@app.the-godfather.ai.attacker.invalid",
        "http://127.0.0.1:3000?next=evil",
        "https://example.invalid:bad",
        "https://example.invalid:0",
        "https://bad host.invalid",
    ],
)
def test_only_exact_secure_origins_are_configurable(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_password="test", web_origin=origin)


def test_self_hosted_origin_is_explicit_configuration_not_request_input() -> None:
    settings = Settings(database_password="test", web_origin="https://cluster.example.invalid")
    assert settings.google_redirect_uri == "https://cluster.example.invalid/api/auth/callback"


def test_test_authentication_cannot_target_application_database() -> None:
    with pytest.raises(ValidationError):
        Settings(database_password="test", environment="test", database_name="godfather")


def test_founder_allowlist_is_explicit_normalized_and_private() -> None:
    settings = Settings(
        database_password="test", google_bootstrap_email=" Founder@Example.invalid "
    )
    assert settings.google_bootstrap_email == "founder@example.invalid"
    assert settings.google_bootstrap_subject == ""
    assert "founder@example.invalid" not in repr(settings)
    assert Settings(database_password="test").google_bootstrap_email == ""


@pytest.mark.parametrize(
    "email",
    ["*", "@example.invalid", "one@example.invalid,two@example.invalid", "no-domain", "one@host"],
)
def test_invalid_founder_allowlist_is_rejected(email: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_password="test", google_bootstrap_email=email)

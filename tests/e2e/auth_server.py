"""Test-only FastAPI server: real PostgreSQL, Authlib with mocked Google network.

Never use with the application database or import from production runtime.
"""

import os
from typing import Any
from urllib.parse import parse_qs

import httpx2
import uvicorn
from alembic import command
from godfather_api import authentication
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.migrations import migration_config

from tests.oidc_provider import OIDCProvider


def main() -> None:
    settings = Settings(
        test_legacy_credentials=False,
        web_origin="http://127.0.0.1:3010",
        google_client_id="test-google-client",
        google_client_secret="test-secret",
        google_bootstrap_email="first@example.invalid",
    )
    if (
        settings.environment != "test"
        or settings.database_name != "godfather_test"
        or os.getenv("GODFATHER_OIDC_E2E") != "1"
    ):
        raise RuntimeError("Only an explicitly isolated PostgreSQL test server is permitted")
    command.upgrade(migration_config(), "head")
    command.downgrade(migration_config(), "base")
    command.upgrade(migration_config(), "head")
    provider = OIDCProvider()
    original = provider.handle

    def transport(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            code = parse_qs(request.content.decode())["code"][0]
            subject, nonce = code.split("|", 1)
            emails = {
                "first-sub": "first@example.invalid",
                "second-sub": "second@example.invalid",
                "contributor-sub": "contributor@example.invalid",
                "outsider-sub": "outsider@example.invalid",
            }
            provider.codes[code] = {
                "sub": subject,
                "email": emails[subject],
                "email_verified": True,
                "name": "OIDC test " + subject,
                "nonce": nonce,
            }
        return original(request)

    original_factory = authentication.google_client

    def client(settings: Settings) -> Any:
        remote = original_factory(settings)
        remote.client_kwargs["transport"] = httpx2.MockTransport(transport)
        return remote

    authentication.google_client = client
    uvicorn.run(
        create_app(settings), host="0.0.0.0", port=8009, access_log=False, log_level="warning"
    )


if __name__ == "__main__":
    main()

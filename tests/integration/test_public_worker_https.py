"""Public transport retains pairing, credential and rate-limit boundaries."""

import pytest
from godfather_worker.desktop import Pairing
from pydantic import SecretStr

from tests.integration.test_authentication import AuthHarness
from tests.integration.test_authentication import auth as auth
from tests.integration.test_nodes import database as database
from tests.integration.test_nodes import registration

pytestmark = pytest.mark.integration


def test_proxy_rate_identity_requires_secret_and_does_not_limit_all_contributors(
    auth: AuthHarness,
) -> None:
    auth.settings.proxy_token = SecretStr("test-only-proxy-authentication")
    auth.settings.authentication_limit = 1
    pairing = Pairing()
    route = "/api/v1/workers/enrollment/exchange"

    def headers(peer: str, token: str = "forged") -> dict[str, str]:
        return {"X-Godfather-Peer": peer, "X-Godfather-Proxy-Token": token}

    assert (
        auth.client.post(route, json=pairing.model_dump(), headers=headers("192.0.2.1")).status_code
        == 404
    )
    # Arbitrary forwarding headers cannot evade the same real peer's limit.
    assert (
        auth.client.post(route, json=pairing.model_dump(), headers=headers("192.0.2.2")).status_code
        == 429
    )
    for peer in ("192.0.2.1", "192.0.2.2"):
        response = auth.client.post(
            route,
            json=pairing.model_dump(),
            headers=headers(peer, "test-only-proxy-authentication"),
        )
        assert response.status_code == 404


def test_public_invalid_credentials_are_limited_without_weakening_auth(auth: AuthHarness) -> None:
    auth.settings.authentication_limit = 1
    route = "/api/v1/workers/register"
    assert auth.client.post(route, json=registration()).status_code == 401
    assert auth.client.post(route, json=registration()).status_code == 429

"""Isolated automated-test OIDC network fixture. Never imported by runtime code."""

import time
from typing import Any
from urllib.parse import parse_qs

import httpx2
from authlib.oauth2.rfc7636 import create_s256_code_challenge  # type: ignore[import-untyped]
from godfather_api.authentication import google_client
from godfather_api.config import Settings
from joserfc import jwt
from joserfc.jwk import RSAKey


class OIDCProvider:
    def __init__(self) -> None:
        self.key = RSAKey.generate_key(2048, parameters={"kid": "test-signing-key"})
        self.codes: dict[str, dict[str, Any]] = {}
        self.challenges: dict[str, str] = {}
        self.challenge = ""
        self.verifier_checked = False
        self.mode = "valid"

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("openid-configuration"):
            return httpx2.Response(
                200,
                json={
                    "issuer": "https://accounts.google.com",
                    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_endpoint": "https://oauth2.googleapis.com/token",
                    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if request.url.path.endswith("certs"):
            return httpx2.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if request.url.path == "/token":
            form = parse_qs(request.content.decode())
            verifier = form["code_verifier"][0]
            assert form["grant_type"] == ["authorization_code"]
            assert form["redirect_uri"][0].endswith("/api/auth/callback")
            challenge = self.challenges.get(form["code"][0], self.challenge)
            assert not challenge or create_s256_code_challenge(verifier) == challenge
            self.verifier_checked = True
            claims = dict(self.codes[form["code"][0]])
            now = int(time.time())
            claims = {
                "iss": "https://accounts.google.com",
                "aud": "test-google-client",
                "iat": now,
                "exp": now + 300,
                **claims,
            }
            if self.mode == "nonce":
                claims["nonce"] = "wrong"
            if self.mode == "issuer":
                claims["iss"] = "https://attacker.invalid"
            if self.mode == "audience":
                claims["aud"] = "wrong-client"
            if self.mode == "expired":
                claims["exp"] = now - 600
            if self.mode == "unverified":
                claims["email_verified"] = False
            key = RSAKey.generate_key(2048) if self.mode == "signature" else self.key
            signed = jwt.encode({"alg": "RS256", "kid": "test-signing-key"}, claims, key)
            return httpx2.Response(
                200,
                json={
                    "access_token": "test-provider-token",
                    "token_type": "Bearer",
                    "id_token": signed,
                },
            )
        raise AssertionError("Unexpected OIDC request")

    def client(self, settings: Settings) -> Any:
        client = google_client(settings)
        client.client_kwargs["transport"] = httpx2.MockTransport(self.handle)
        return client

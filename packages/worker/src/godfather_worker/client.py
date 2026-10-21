"""Small outbound HTTP client; credentials never follow redirects or proxy settings."""

import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from godfather_contracts import Contract, WorkerAck


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        return None


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Use an origin URL without credentials, paths, queries or fragments")
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise ValueError("Coordinator port must be between 1 and 65535")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("HTTP is permitted only on loopback; remote origins require HTTPS")
    return url.rstrip("/")


class WorkerClient:
    def __init__(self, url: str, token: str) -> None:
        self.url = validate_url(url)
        self.token = token
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def post(self, path: str, payload: Contract) -> WorkerAck:
        return WorkerAck.model_validate(self.post_document(path, payload))

    def post_document(self, path: str, payload: Contract) -> object:
        request = Request(
            self.url + path,
            data=payload.model_dump_json().encode("utf-8"),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method="POST",
        )
        with self.opener.open(request, timeout=10) as response:
            limit = 9 * 1024**2 if path.endswith(("/jobs/poll", "/workflow/artifact")) else 1024**2
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError("Coordinator response exceeds the protocol limit")
            return json.loads(data)


def retryable(error: HTTPError) -> bool:
    return error.code in (408, 429) or error.code >= 500

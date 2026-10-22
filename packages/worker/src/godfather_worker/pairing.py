"""Bounded approval polling: retry only explicit pending/rate-limit responses."""

import threading
import time
from collections.abc import Callable
from urllib.error import HTTPError

from godfather_worker.desktop import Pairing, SecretStore


def check_connection(origin: str) -> None:
    """Probe fresh pairing without an account, approval, registration or saved secret."""

    class RefuseStore:
        def read(self) -> str | None:
            return None

        def write(self, value: str) -> None:
            raise RuntimeError("An unapproved diagnostic must never store a credential")

        def delete(self) -> None:
            raise RuntimeError("An unapproved diagnostic must never delete a credential")

    try:
        Pairing(origin=origin).exchange(RefuseStore())
    except HTTPError as error:
        if error.code == 404:
            return
        raise
    raise RuntimeError("Coordinator unexpectedly accepted an unapproved diagnostic")


def await_approval(
    pairing: Pairing,
    store: SecretStore,
    cancel: threading.Event,
    *,
    clock: Callable[[], float] = time.monotonic,
    timeout: float = 300,
) -> dict[str, str] | None:
    deadline = clock() + timeout
    while not cancel.is_set() and clock() < deadline:
        try:
            return pairing.exchange(store)
        except HTTPError as error:
            if error.code not in (404, 429):
                raise
            # A 404 means no usable approval yet. Never replay a lost response or
            # a secure-store failure: it might already have consumed the grant.
            delay = 60 if error.code == 429 else 5
            cancel.wait(min(delay, max(0, deadline - clock())))
    if cancel.is_set():
        return None
    raise TimeoutError("Approval timed out. Click Connect to start again.")

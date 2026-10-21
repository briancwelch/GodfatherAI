"""Bounded approval polling: retry only explicit pending/rate-limit responses."""

import threading
import time
from collections.abc import Callable
from urllib.error import HTTPError

from godfather_worker.desktop import Pairing, SecretStore


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

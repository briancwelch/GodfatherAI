"""Owner-local API key entry, independent of Google and machine authentication."""

import argparse
import getpass
import importlib
import platform
from typing import cast
from uuid import UUID

from godfather_model_gateway import ProviderConfig
from keyring.backend import KeyringBackend


def store() -> KeyringBackend:
    implementations = {
        "Windows": ("keyring.backends.Windows", "WinVaultKeyring"),
        "Darwin": ("keyring.backends.macOS", "Keyring"),
        "Linux": ("keyring.backends.SecretService", "Keyring"),
    }
    try:
        module, name = implementations[platform.system()]
        backend = cast(KeyringBackend, getattr(importlib.import_module(module), name)())
        if backend.priority <= 0:
            raise RuntimeError
        return backend
    except Exception:
        raise OSError("A supported, unlocked OS credential store is required") from None


def load(config: ProviderConfig) -> None:
    if config.provider not in ("openai", "anthropic"):
        return
    try:
        key = store().get_password(
            "ai.the-godfather.provider." + config.provider, str(config.connection_id)
        )
        if not isinstance(key, str) or not key.strip():
            raise OSError
        config.set_api_key(key)
    except Exception:
        raise OSError("Provider API credential unavailable in the owner's OS store") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("set", "delete"))
    parser.add_argument("provider", choices=("openai", "anthropic"))
    parser.add_argument("connection_id", type=UUID)
    args = parser.parse_args(argv)
    try:
        backend = store()
        service = "ai.the-godfather.provider." + args.provider
        if args.action == "set":
            key = getpass.getpass("Provider API key (hidden; separate from Google Sign-In): ")
            if not key.strip() or "\n" in key or "\r" in key:
                raise OSError
            backend.set_password(service, str(args.connection_id), key)
        else:
            backend.delete_password(service, str(args.connection_id))
        print("Provider credential updated in the local OS store. Restart the worker to refresh.")
        return 0
    except Exception:
        print("Credential update failed. Unlock a supported OS store and retry locally.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

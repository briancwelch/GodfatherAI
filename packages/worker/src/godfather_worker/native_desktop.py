"""Small OS adapters; no credentials in files, arguments or subprocesses."""

import contextlib
import importlib
import os
import platform
import sys
from pathlib import Path
from typing import Any

from godfather_worker.desktop import login_startup
from godfather_worker.keychain import Keychain
from godfather_worker.provider_credentials import store

SERVICE = "ai.the-godfather.worker"
ACCOUNT = "machine-credential-v1"


class CredentialStore:
    def read(self) -> str | None:
        if platform.system() == "Darwin":
            return Keychain().read()
        value = store().get_password(SERVICE, ACCOUNT)
        return value if isinstance(value, str) else None

    def write(self, value: str) -> None:
        if self.read() is not None:
            raise OSError("An identity already exists. Disconnect it before connecting another.")
        if platform.system() == "Darwin":
            Keychain().write(value)
        else:
            store().set_password(SERVICE, ACCOUNT, value)

    def delete(self) -> None:
        if platform.system() == "Darwin":
            Keychain().delete()
        elif self.read() is not None:
            store().delete_password(SERVICE, ACCOUNT)


def data_folder() -> Path:
    system = platform.system()
    if system == "Windows":
        return Path(os.environ["LOCALAPPDATA"]) / "The Godfather" / "Desktop Worker"
    if system == "Darwin":
        return Path.home() / "Library/Application Support/The Godfather Worker"
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "godfather-worker"
    )


def set_login_startup(enable: bool) -> None:
    executable = Path(sys.executable)
    if not getattr(sys, "frozen", False):
        raise ValueError("Install the packaged app before enabling login startup")
    if platform.system() == "Darwin":
        login_startup(
            enable, executable, Path.home() / "Library/LaunchAgents/ai.the-godfather.worker.plist"
        )
    elif platform.system() == "Windows":
        registry = importlib.import_module("winreg")
        with registry.CreateKey(
            registry.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            if enable:
                registry.SetValueEx(
                    key, "The Godfather Worker", 0, registry.REG_SZ, f'"{executable}" --login'
                )
            else:
                with contextlib.suppress(FileNotFoundError):
                    registry.DeleteValue(key, "The Godfather Worker")
    else:
        raise ValueError("Login startup is currently supported by the Windows and Mac installers")


def acquire_lock(folder: Path) -> Any:
    """Keep the open handle for the life of the app; OS releases it after a crash."""
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = (folder / "app.lock").open("a+b")
    try:
        if platform.system() == "Windows":
            native = importlib.import_module("msvcrt")
            handle.seek(0)
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            native.locking(handle.fileno(), native.LK_NBLCK, 1)
        else:
            native = importlib.import_module("fcntl")
            native.flock(handle, native.LOCK_EX | native.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        return None

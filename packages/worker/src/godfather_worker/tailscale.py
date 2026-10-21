"""Read-only local Tailscale discovery. No login, routing changes or peer inventory."""

import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TailscaleStatus:
    installed: bool
    connected: bool
    message: str


def executable() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    candidates: list[Path] = []
    if platform.system() == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Tailscale/tailscale.exe"
        ]
    elif platform.system() == "Darwin":
        candidates = [
            Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale"),
            Path("/usr/local/bin/tailscale"),
            Path("/opt/homebrew/bin/tailscale"),
        ]
    else:
        candidates = [Path("/usr/bin/tailscale"), Path("/usr/local/bin/tailscale")]
    return next((str(p) for p in candidates if p.is_file()), None)


def detect() -> TailscaleStatus:
    command = executable()
    if command is None:
        return TailscaleStatus(False, False, "Tailscale not installed. Using authenticated HTTPS.")
    try:
        result = subprocess.run(
            [command, "status", "--json", "--peers=false"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            # macOS app binary must enter CLI mode even when launched from a tray app.
            env={**os.environ, "TAILSCALE_BE_CLI": "1"},
        )
        status = json.loads(result.stdout)
        if not isinstance(status, dict):
            raise ValueError("Unsupported status")
        self_status = status.get("Self") or {}
        connected = status.get("BackendState") == "Running" and self_status.get("Online") is True
        if connected:
            return TailscaleStatus(
                True,
                True,
                "Tailscale connected to a tailnet. Private routes are preferred where configured. "
                "HTTPS remains available.",
            )
        return TailscaleStatus(
            True,
            False,
            "Tailscale installed, not connected to a tailnet. Using authenticated HTTPS.",
        )
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return TailscaleStatus(
            True,
            False,
            "Tailscale installed; connection status unavailable. HTTPS remains available.",
        )

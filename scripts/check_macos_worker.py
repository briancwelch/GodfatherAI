"""Smoke test a built macOS DMG without enrollment, credentials or external services."""

import argparse
import json
import os
import platform
import plistlib
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_macos_worker import APP_NAME, native_architecture
from scripts.dev import ROOT
from scripts.release import sha256, version

# Thin/fat Mach-O headers, both byte orders, including universal2 libraries.
MACHO = {
    bytes.fromhex(value)
    for value in (
        "feedface",
        "cefaedfe",
        "feedfacf",
        "cffaedfe",
        "cafebabe",
        "bebafeca",
        "cafebabf",
        "bfbafeca",
    )
}


def execute(*arguments: str) -> str:
    return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=120).stdout


def verify_checksum(dmg: Path) -> None:
    expected = Path(str(dmg) + ".sha256").read_text(encoding="utf-8").strip()
    if expected != f"{sha256(dmg)}  {dmg.name}":
        raise RuntimeError("DMG SHA-256 mismatch")


def inspect_bundle(app: Path, architecture: str) -> None:
    """Reject escaping symlinks, accidental local inputs and external runtime links."""
    base = app.resolve()
    binaries = 0
    for path in app.rglob("*"):
        if not path.resolve().is_relative_to(base):
            raise RuntimeError(f"Bundle symlink escapes app: {path}")
        public_ca_bundle = path.name == "cacert.pem" and path.parent.name == "certifi"
        if path.name in {
            ".env",
            ".git",
            "production.env",
            "credentials.json",
        } or (path.name.endswith((".pem", ".key", ".p12", ".pfx")) and not public_ca_bundle):
            raise RuntimeError(f"Forbidden build input in app: {path}")
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            magic = stream.read(4)
        if magic not in MACHO:
            continue
        binaries += 1
        if architecture not in execute("/usr/bin/lipo", "-archs", str(path)).split():
            raise RuntimeError(f"Wrong native library architecture: {path}")
        for line in execute("/usr/bin/otool", "-L", str(path)).splitlines()[1:]:
            if not line.startswith("\t"):
                continue  # Additional architecture headers in universal binaries.
            dependency = line.strip().split(" (", 1)[0]
            if dependency.startswith("/") and not dependency.startswith(
                ("/System/Library/", "/usr/lib/")
            ):
                raise RuntimeError(f"External runtime dependency in {path}: {dependency}")
        commands = execute("/usr/bin/otool", "-l", str(path)).splitlines()
        for index, line in enumerate(commands):
            if line.strip() == "cmd LC_RPATH":
                search_path = commands[index + 2].strip().split(" ")[1]
                if search_path.startswith("/") and not search_path.startswith(
                    ("/System/Library/", "/usr/lib/")
                ):
                    raise RuntimeError(f"External runtime search path in {path}: {search_path}")
    if not binaries:
        raise RuntimeError("App contains no native binaries")


def check(release: str, architecture: str) -> None:
    if native_architecture() != architecture:
        raise RuntimeError("Smoke test must run on the requested native architecture")
    suffix = "arm64" if architecture == "arm64" else "x64"
    dmg = ROOT / "dist" / f"godfather-worker-{release}-macos-{suffix}-installer.dmg"
    verify_checksum(dmg)
    manifest = json.loads(Path(str(dmg) + ".manifest.json").read_text(encoding="utf-8"))
    if (
        manifest["version"] != release
        or manifest["architecture"] != architecture
        or manifest["worker_protocol"] != 1
        or "no Developer ID or notarization" not in manifest["signing"]
    ):
        raise RuntimeError("Incorrect candidate manifest")
    execute("/usr/bin/hdiutil", "verify", str(dmg))
    with TemporaryDirectory(prefix="godfather-macos-smoke-") as temporary:
        folder = Path(temporary)
        mount = folder / "mounted"
        mount.mkdir()
        execute(
            "/usr/bin/hdiutil",
            "attach",
            "-readonly",
            "-nobrowse",
            "-mountpoint",
            str(mount),
            str(dmg),
        )
        try:
            for name in ("README.md", "TROUBLESHOOTING.md", "ADMINISTRATOR.md", "manifest.json"):
                if not (mount / name).is_file():
                    raise RuntimeError(f"Missing packaged guide/manifest: {name}")
            if json.loads((mount / "manifest.json").read_text(encoding="utf-8")) != manifest:
                raise RuntimeError("DMG and external manifest differ")
            app = folder / f"{APP_NAME}.app"
            execute("/usr/bin/ditto", str(mount / app.name), str(app))
        finally:
            execute("/usr/bin/hdiutil", "detach", str(mount))
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
        if info["CFBundleIdentifier"] != "ai.the-godfather.worker":
            raise RuntimeError("Unexpected app identity")
        execute("/usr/bin/codesign", "--verify", "--deep", "--strict", str(app))
        inspect_bundle(app, architecture)
        # Launch the copy after unmounting the DMG, outside the checkout. No build
        # interpreter/site-packages, Homebrew PATH or Python environment is available.
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PYTHON", "UV_", "DYLD_", "TCL", "TK"))
        }
        environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        subprocess.run(
            [str(app / "Contents/MacOS" / APP_NAME), "--self-test"],
            cwd=folder,
            env=environment,
            check=True,
            timeout=120,
        )
    print(f"Verified native {platform.machine()} DMG and isolated bundled Tk/framework startup")
    print("Unsigned development candidate; no enrollment, inference or Gatekeeper acceptance")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, type=version)
    parser.add_argument("--architecture", required=True, choices=("arm64", "x86_64"))
    arguments = parser.parse_args()
    check(arguments.version, arguments.architecture)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

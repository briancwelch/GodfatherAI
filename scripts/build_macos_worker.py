"""Build a native macOS app and DMG locally; never publishes or installs anything."""

import argparse
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from scripts import build_worker
from scripts.dev import ROOT
from scripts.release import sha256, version

APP_NAME = "The Godfather Worker"


def native_architecture() -> str:
    if platform.system() != "Darwin" or platform.machine() not in ("arm64", "x86_64"):
        raise RuntimeError(
            "Build on a native arm64 or x86_64 Mac; cross-built installers are refused"
        )
    return platform.machine()


def build(release: str, identity: str | None = None, notary_profile: str | None = None) -> Path:
    architecture = native_architecture()
    if notary_profile and not identity:
        raise ValueError("Notarization requires a Developer ID signing identity")
    suffix = "macos-arm64" if architecture == "arm64" else "macos-x64"
    output = ROOT / "dist" / f"godfather-worker-{release}-{suffix}-installer"
    dmg = Path(str(output) + ".dmg")
    if output.exists() or dmg.exists():
        raise RuntimeError("Installer output already exists; use a new release version")
    # Reuse the reviewed, worker-only locked dependency closure and build environment.
    # This also creates the existing separately versioned CLI archive.
    build_worker.build(release)
    workspace = ROOT / ".cache/worker-build" / f"{release}-{suffix}"
    python = workspace / ".venv/bin/python"

    def execute(*arguments: str) -> str:
        try:
            return subprocess.run(
                arguments,
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYINSTALLER_CONFIG_DIR": str(workspace / "pyinstaller-cache")},
            ).stdout
        except subprocess.CalledProcessError as error:
            print(error.stdout or "", file=sys.stderr)
            print(error.stderr or "", file=sys.stderr)
            raise

    # uv's standalone Python may lack Tcl/Tk. Fail clearly before producing a DMG.
    try:
        execute(
            str(python),
            "-c",
            "import tkinter; r=tkinter.Tk(); r.withdraw(); r.update(); r.destroy()",
        )
    except subprocess.CalledProcessError:
        raise RuntimeError(
            "Build Python needs working Tcl/Tk. Set GODFATHER_BUILD_PYTHON to a native Python 3.14 "
            "with Tk support. No installer produced."
        ) from None
    entry = workspace / "macos-entry.py"
    entry.write_text(
        "from godfather_worker.macos_app import main\nraise SystemExit(main())\n", encoding="utf-8"
    )
    arguments = [
        str(python),
        "-m",
        "PyInstaller",
        "--onedir",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--name",
        APP_NAME,
        "--target-arch",
        architecture,
        "--osx-bundle-identifier",
        "ai.the-godfather.worker",
        "--distpath",
        str(workspace / "app"),
        "--workpath",
        str(workspace / "app-build"),
        "--specpath",
        str(workspace),
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "pip",
        "--exclude-module",
        "setuptools",
        "--hidden-import",
        "fcntl",
        "--hidden-import",
        "keyring.backends.macOS",
    ]
    if identity:
        arguments += ["--codesign-identity", identity]
    execute(*arguments, str(entry))
    source = workspace / "app" / f"{APP_NAME}.app"
    output.mkdir(parents=True)
    app = output / source.name
    shutil.copytree(source, app, symlinks=True)
    info = app / "Contents/Info.plist"
    metadata = plistlib.loads(info.read_bytes())
    metadata.update(
        CFBundleShortVersionString=release.split("-")[0],
        CFBundleVersion=release.split("-")[0],
        NSHighResolutionCapable=True,
        LSMinimumSystemVersion="13.0",
    )
    info.write_bytes(plistlib.dumps(metadata))
    # Updating Info.plist invalidates the outer signature; nested libraries were
    # signed by PyInstaller. Ad-hoc signing is not Developer ID distribution signing.
    signing = identity or "-"
    signing_options = ["--options", "runtime", "--timestamp"] if identity else []
    execute("/usr/bin/codesign", "--force", "--sign", signing, *signing_options, str(app))
    execute("/usr/bin/codesign", "--verify", "--deep", "--strict", str(app))
    executable = app / "Contents/MacOS" / APP_NAME
    detected = execute("/usr/bin/lipo", "-archs", str(executable)).strip().split()
    if architecture not in detected:
        raise RuntimeError("Built executable architecture does not match this Mac")
    execute(str(executable), "--self-test")
    docs = ROOT / "packages/worker/macos"
    for name in ("README.md", "TROUBLESHOOTING.md", "ADMINISTRATOR.md"):
        shutil.copyfile(docs / name, output / name)
    signing_status = (
        "Developer ID signed; notarization pending"
        if identity
        else "Ad-hoc signed development candidate; no Developer ID or notarization"
    )
    manifest = {
        "version": release,
        "architecture": architecture,
        "minimum_macos": "13.0",
        "worker_protocol": 1,
        "signing": signing_status,
        "validation": "Native framework/arch/signature checks; physical acceptance pending",
        "pyinstaller": build_worker.PYINSTALLER,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    execute(
        "/usr/bin/hdiutil",
        "create",
        "-volname",
        APP_NAME,
        "-srcfolder",
        str(output),
        "-ov",
        "-format",
        "UDZO",
        str(dmg),
    )
    if notary_profile:
        result = json.loads(
            execute(
                "/usr/bin/xcrun",
                "notarytool",
                "submit",
                str(dmg),
                "--keychain-profile",
                notary_profile,
                "--wait",
                "--output-format",
                "json",
            )
        )
        if result.get("status") != "Accepted":
            raise RuntimeError("Apple did not accept notarization; do not distribute the candidate")
        execute("/usr/bin/xcrun", "stapler", "staple", str(dmg))
        execute("/usr/bin/xcrun", "stapler", "validate", str(dmg))
        manifest["signing"] = "Developer ID signed; DMG notarization accepted and stapled"
    # External manifest reflects final ticket status without changing the signed DMG.
    Path(str(dmg) + ".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    Path(str(dmg) + ".sha256").write_text(f"{sha256(dmg)}  {dmg.name}\n", encoding="utf-8")
    print(f"Native installer candidate: {dmg}\n{manifest['signing']}")
    return dmg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, type=version)
    parser.add_argument("--sign-identity")
    parser.add_argument("--notary-profile")
    arguments = parser.parse_args()
    build(arguments.version, arguments.sign_identity, arguments.notary_profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

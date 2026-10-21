"""Stage checksum-verified native candidates for inclusion in a coordinator release."""

import argparse
import json
import re
import shutil
from pathlib import Path

from scripts.release import sha256


def stage(files: list[Path], output: Path) -> None:
    if output.exists():
        raise RuntimeError("Downloads output exists; use a new staging folder")
    artifacts: list[dict[str, str]] = []
    for path in files:
        match = re.fullmatch(
            r"(?:godfather-worker|consigliere)-([a-z0-9.-]+)-(windows-x64-setup\.exe|macos-(arm64|x64)-installer\.dmg)",
            path.name,
        )
        if not match:
            raise ValueError("Select only native worker installers")
        digest = sha256(path)
        if Path(str(path) + ".sha256").read_text().strip() != f"{digest}  {path.name}":
            raise ValueError("Worker checksum mismatch")
        manifest = json.loads(Path(str(path) + ".manifest.json").read_text())
        if manifest["version"] != match[1] or not isinstance(manifest.get("signing"), str):
            raise ValueError("Worker manifest mismatch")
        platform = (
            "Windows x64"
            if path.suffix == ".exe"
            else ("Mac (Apple silicon)" if match[3] == "arm64" else "Mac (Intel)")
        )
        artifacts.append(
            {
                "platform": platform,
                "filename": path.name,
                "sha256": digest,
                "signing": manifest["signing"],
            }
        )
    if len({item["platform"] for item in artifacts}) != len(artifacts):
        raise ValueError("Choose one installer per platform")
    output.mkdir(parents=True)
    for path in files:
        shutil.copyfile(path, output / path.name)
    (output / "manifest.json").write_text(json.dumps({"artifacts": artifacts}, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("installers", nargs="+", type=Path)
    args = parser.parse_args()
    stage(args.installers, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

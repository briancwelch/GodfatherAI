"""Read native build identity; source checkouts have no released build version."""

import json
import re
from pathlib import Path


def worker_version() -> str | None:
    try:
        value = json.loads(Path(__file__).with_name("build-info.json").read_text(encoding="utf-8"))[
            "version"
        ]
        if (
            isinstance(value, str)
            and len(value) <= 100
            and re.fullmatch(
                r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", value
            )
        ):
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None

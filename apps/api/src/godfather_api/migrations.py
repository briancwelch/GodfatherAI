"""Resolve the repository migration directory without depending on the current directory."""

import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def migration_config() -> Config:
    root = Path(__file__).resolve().parents[4]
    directory = Path(
        os.environ.get("GODFATHER_MIGRATIONS_DIRECTORY", root / "infrastructure" / "migrations")
    )
    config = Config(str(directory / "alembic.ini"))
    config.set_main_option("script_location", str(directory))
    return config


def migration_head() -> str:
    head = ScriptDirectory.from_config(migration_config()).get_current_head()
    if head is None:
        raise RuntimeError("No migration head is configured")
    return head

"""Appearance constraints prevent CSS injection and unreadable saved palettes."""

from pathlib import Path

import pytest
from godfather_api.appearance import Appearance, Palette
from godfather_worker import build_info
from pydantic import ValidationError


def test_default_palettes_and_full_settings_round_trip() -> None:
    settings = Appearance()
    assert Appearance.model_validate_json(settings.model_dump_json()) == settings
    with pytest.raises(ValidationError):
        Palette(foreground="#ffffff")
    with pytest.raises(ValidationError):
        Palette(background="url(https://untrusted.invalid)")
    for field, value in (
        ("font_size", 8),
        ("navigation_width", 500),
        ("font", "remote"),
        ("unknown_css", "anything"),
    ):
        with pytest.raises(ValidationError):
            Appearance.model_validate({field: value})


def test_native_build_version_is_read_without_guessing_source_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(build_info, "__file__", str(tmp_path / "build_info.py"))
    assert build_info.worker_version() is None
    manifest = tmp_path / "build-info.json"
    manifest.write_text('{"version":"0.4.1-rc.10"}')
    assert build_info.worker_version() == "0.4.1-rc.10"
    for value in ('{"version":"unknown"}', "{}", "[]", "invalid"):
        manifest.write_text(value)
        assert build_info.worker_version() is None

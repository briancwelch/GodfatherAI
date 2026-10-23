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
        ("button_variant", "custom-css"),
        ("control_size", "huge"),
        ("panel_padding", 100),
        ("panel_shadow", "url(https://untrusted.invalid)"),
        ("toast_position", "arbitrary"),
        ("toast_width", 10000),
        ("progress_height", 1),
        ("danger_color", "url(https://untrusted.invalid)"),
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


def test_pre_bootstrap_settings_receive_compatible_defaults() -> None:
    settings = Appearance.model_validate({"font_size": 15, "striped_tables": True})
    assert settings.font_size == 15
    assert settings.striped_tables is True
    assert settings.button_variant == "solid"
    assert settings.toast_position == "bottom-end"
    assert settings.progress_height == 12
    assert settings.progress_striped is True

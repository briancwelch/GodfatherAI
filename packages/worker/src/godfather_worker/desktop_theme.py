"""Godfather desktop tokens and owner-local presentation preferences."""

import json
import os
from pathlib import Path
from tkinter import ttk
from typing import Literal

from godfather_contracts import Contract
from pydantic import Field


class Preferences(Contract):
    theme: Literal["light", "dark"] = "light"
    font_size: int = Field(default=10, ge=9, le=14)
    close_to_tray: bool = True
    start_minimized: bool = False
    remember_size: bool = True
    automatic_updates: bool = False
    width: int = Field(default=1120, ge=640, le=16384)
    height: int = Field(default=760, ge=480, le=16384)


def load(folder: Path) -> Preferences:
    try:
        return Preferences.model_validate_json((folder / "appearance.json").read_text())
    except (ValueError, OSError):
        return Preferences()


def save(folder: Path, preferences: Preferences) -> None:
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = folder / "appearance.json.tmp"
    temporary.write_text(json.dumps(preferences.model_dump()), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(folder / "appearance.json")


def apply(style: ttk.Style, preferences: Preferences) -> dict[str, str]:
    dark = preferences.theme == "dark"
    colors = {
        "workspace": "#16191D" if dark else "#F4F8FC",
        "panel": "#202429" if dark else "#FFFFFF",
        "text": "#EEF3F7" if dark else "#14283D",
        "muted": "#ABB8C6" if dark else "#657A90",
        "border": "#3A424B" if dark else "#D4DFE9",
        "selected": "#253A40" if dark else "#E1F0F5",
    }
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", preferences.font_size))
    style.configure("TFrame", background=colors["workspace"])
    style.configure("Panel.TFrame", background=colors["panel"])
    style.configure("TLabel", background=colors["workspace"], foreground=colors["text"])
    style.configure("Muted.TLabel", foreground=colors["muted"])
    style.configure("Title.TLabel", font=("Segoe UI", preferences.font_size + 2, "bold"))
    style.configure("TLabelframe", background=colors["workspace"], bordercolor=colors["border"])
    style.configure("TLabelframe.Label", background=colors["workspace"], foreground=colors["muted"])
    style.configure(
        "TButton",
        padding=(12, 6),
        foreground=colors["text"],
        background=colors["workspace"],
        bordercolor=colors["border"],
    )
    style.map("TButton", background=[("active", colors["selected"])])
    style.configure("Ribbon.TButton", padding=(12, 7), width=11, foreground="#1468CC")
    style.configure(
        "RibbonCaption.TLabel",
        background=colors["selected"],
        foreground=colors["muted"],
        anchor="center",
        font=("Segoe UI", max(9, preferences.font_size - 1)),
    )
    style.configure(
        "TCheckbutton", background=colors["workspace"], foreground=colors["text"], padding=(0, 4)
    )
    style.configure(
        "TEntry",
        fieldbackground=colors["panel"],
        foreground=colors["text"],
        bordercolor=colors["border"],
        padding=5,
    )
    style.configure(
        "TCombobox", fieldbackground=colors["panel"], foreground=colors["text"], padding=5
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", colors["panel"])],
        foreground=[("readonly", colors["text"])],
    )
    style.configure("TNotebook", background=colors["workspace"], borderwidth=0)
    style.configure(
        "TNotebook.Tab", padding=(14, 7), background=colors["workspace"], foreground=colors["text"]
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", colors["panel"])],
        foreground=[("selected", "#087F8C")],
    )
    style.configure(
        "Treeview",
        background=colors["panel"],
        fieldbackground=colors["panel"],
        foreground=colors["text"],
        rowheight=preferences.font_size * 2 + 8,
        bordercolor=colors["border"],
    )
    style.configure(
        "Treeview.Heading",
        background=colors["workspace"],
        foreground=colors["text"],
        padding=(8, 6),
    )
    style.map(
        "Treeview",
        background=[("selected", colors["selected"])],
        foreground=[("selected", colors["text"])],
    )
    return colors

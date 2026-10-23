"""Validated shared appearance; only platform administrators can change it."""

from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text

from godfather_api.authentication import audit, require_permission
from godfather_api.models import ApplicationSetting
from godfather_api.nodes import SessionDep, authenticate

router = APIRouter(prefix="/api/v1/appearance")
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


def luminance(value: str) -> float:
    channels = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


class Palette(BaseModel):
    model_config = ConfigDict(extra="forbid")
    background: Color = "#f4f8fc"
    foreground: Color = "#14283d"
    card: Color = "#ffffff"
    muted: Color = "#e8f0f7"
    muted_foreground: Color = "#52677d"
    border: Color = "#d4dfe9"
    primary: Color = "#077582"
    primary_foreground: Color = "#ffffff"
    sidebar: Color = "#f4f8fc"
    focus: Color = "#087f8c"
    header: Color = "#14283d"
    header_text: Color = "#f4f8fc"
    highlight: Color = "#58d5de"

    @model_validator(mode="after")
    def readable(self) -> "Palette":
        for ink, surfaces in (
            (self.foreground, (self.background, self.card, self.sidebar, self.muted)),
            (self.muted_foreground, (self.background, self.card, self.sidebar)),
            (self.primary, (self.background, self.card, self.sidebar, self.muted)),
            (self.primary_foreground, (self.primary,)),
            (self.header_text, (self.header,)),
            (self.highlight, (self.header,)),
        ):
            for surface in surfaces:
                a, b = sorted((luminance(ink), luminance(surface)))
                if (b + 0.05) / (a + 0.05) < 4.5:
                    raise ValueError("Text and action colors require at least 4.5:1 contrast")
        return self


class Appearance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    light: Palette = Field(default_factory=Palette)
    dark: Palette = Field(
        default_factory=lambda: Palette(
            background="#141414",
            foreground="#f4f8fc",
            card="#202020",
            muted="#2b2b2b",
            muted_foreground="#b6c8d9",
            border="#444444",
            primary="#58d5de",
            primary_foreground="#14283d",
            sidebar="#1b1b1b",
            focus="#58d5de",
            header="#202020",
        )
    )
    default_theme: Literal["light", "dark"] = "light"
    font: Literal["system", "arial", "verdana", "georgia", "mono"] = "system"
    font_size: int = Field(default=13, ge=12, le=18)
    line_height: float = Field(default=1.5, ge=1.3, le=1.8)
    density: Literal["compact", "comfortable", "spacious"] = "compact"
    navigation_width: int = Field(default=190, ge=150, le=360)
    inspector_width: int = Field(default=250, ge=180, le=360)
    radius: int = Field(default=3, ge=0, le=16)
    content_width: Literal["full", "1440", "1680"] = "full"
    navigation_open: bool = True
    inspector_open: bool = False
    striped_tables: bool = False
    sticky_header: bool = False
    reduced_motion: bool = False
    ribbon_size: Literal["normal", "compact"] = "normal"
    button_variant: Literal["solid", "outline"] = "solid"
    control_size: Literal["small", "medium", "large"] = "medium"
    panel_shadow: Literal["none", "small", "medium"] = "small"
    panel_padding: int = Field(default=20, ge=12, le=32)
    table_hover: bool = True
    table_borders: bool = False
    toast_position: Literal["top-start", "top-end", "bottom-start", "bottom-end"] = "bottom-end"
    toast_width: int = Field(default=380, ge=280, le=560)
    progress_height: int = Field(default=12, ge=8, le=24)
    progress_striped: bool = True
    progress_animated: bool = True
    success_color: Color = "#198754"
    warning_color: Color = "#ffc107"
    danger_color: Color = "#dc3545"
    info_color: Color = "#0dcaf0"


@router.get("")
def get_appearance(request: Request, session: SessionDep) -> Appearance:
    authenticate(request, session, "human")
    row = session.get(ApplicationSetting, "appearance")
    return Appearance.model_validate(row.value) if row else Appearance()


@router.post("")
def save_appearance(payload: Appearance, request: Request, session: SessionDep) -> Appearance:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "platform.manage")
    session.execute(text("SELECT pg_advisory_xact_lock(909002)"))
    row = session.scalar(
        select(ApplicationSetting).where(ApplicationSetting.key == "appearance").with_for_update()
    )
    if row is None:
        session.add(ApplicationSetting(key="appearance", value=payload.model_dump()))
    else:
        row.value = payload.model_dump()
    audit(session, "appearance_updated", actor.owner_id, actor.owner_id)
    return payload

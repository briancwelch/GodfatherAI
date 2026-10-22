"""Self-service profile edits; the target is always the authenticated account."""

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from godfather_contracts import Contract
from pydantic import Field, field_validator

from godfather_api.authentication import audit, human, user_data
from godfather_api.models import User
from godfather_api.nodes import SessionDep

router = APIRouter(prefix="/api/v1/account")


class ProfileChange(Contract):
    display_name: str = Field(min_length=1, max_length=200)
    picture: str | None = Field(default=None, max_length=2048)
    location: str = Field(default="", max_length=120)

    @field_validator("display_name", "location")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if any(ord(c) < 32 for c in value):
            raise ValueError("Use plain text without control characters")
        return value

    @field_validator("picture")
    @classmethod
    def safe_picture(cls, value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Use an HTTPS avatar image address without credentials")
        return value


@router.post("/profile")
def save_profile(
    payload: ProfileChange, request: Request, session: SessionDep
) -> dict[str, object]:
    actor = human(request, session)
    user = session.get(User, actor.owner_id, with_for_update=True)
    if user is None or not user.enabled:
        raise HTTPException(403, "Account unavailable")
    if not payload.display_name:
        raise HTTPException(422, "Display name must not be blank")
    user.display_name, user.picture = payload.display_name, payload.picture
    user.profile = {"customized": True, "location": payload.location}
    audit(session, "account_profile_changed", user.id, user.id)
    return user_data(user)

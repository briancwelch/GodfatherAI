"""Google-only human authentication. Workers retain independent machine credentials."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID

from authlib.integrations.starlette_client import OAuth  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from godfather_api.config import Settings
from godfather_api.logging import correlation_id
from godfather_api.models import (
    AccessCredential,
    AdministratorBootstrap,
    AuthenticationLimit,
    Event,
    GoogleIdentity,
    HumanSession,
    Invitation,
    LoginTransaction,
    User,
)
from godfather_api.nodes import SessionDep, token_digest

router = APIRouter(prefix="/api/v1/auth")
SESSION_COOKIE = "godfather_session"
LOGIN_COOKIE = "godfather_login"
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "platform_admin": {"platform.manage", "nodes.contribute", "jobs.use", "workspaces.create"},
    "contributor": {"nodes.contribute", "jobs.use", "workspaces.create"},
    "member": {"jobs.use", "workspaces.create"},
}


def roles(user: User) -> list[str]:
    return sorted(set([user.role, *user.roles]))


def permissions(user: User) -> list[str]:
    return sorted(set().union(*(ROLE_PERMISSIONS.get(role, set()) for role in roles(user))))


def require_permission(session: Session, owner_id: UUID, permission: str) -> User:
    user = session.get(User, owner_id)
    if user is None or not user.enabled or permission not in permissions(user):
        raise HTTPException(403, "Permission denied")
    return user


def user_data(user: User) -> dict[str, object]:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "picture": user.picture,
        "enabled": user.enabled,
        "roles": roles(user),
        "permissions": permissions(user),
    }


def audit(
    session: Session,
    action: str,
    actor: UUID | None = None,
    target: UUID | None = None,
    outcome: str = "success",
    workspace_id: UUID | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    session.add(
        Event(
            actor_id=actor,
            workspace_id=workspace_id,
            type="security." + action,
            correlation_id=correlation_id.get(),
            details={
                "target_id": str(target) if target else None,
                "outcome": outcome,
                **(metadata or {}),
            },
        )
    )


def origin_required(request: Request) -> None:
    if request.headers.get("origin") != request.app.state.settings.web_origin:
        raise HTTPException(403, "Trusted application origin required")


def human(request: Request, session: Session) -> HumanSession | AccessCredential:
    token = request.headers.get("x-godfather-session") or request.cookies.get(SESSION_COOKIE, "")
    if len(token) != 43 or not token.isascii():
        raise HTTPException(401, "Sign in required")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin_required(request)
    row = session.scalar(
        select(HumanSession).where(HumanSession.token_hash == token_digest(token)).with_for_update()
    )
    if row is None or row.revoked or row.expires_at <= datetime.now(UTC):
        raise HTTPException(401, "Session expired or revoked")
    user = session.get(User, row.owner_id)
    if user is None or not user.enabled:
        raise HTTPException(401, "Session expired or revoked")
    return row


def cookie(
    response: JSONResponse | RedirectResponse,
    name: str,
    token: str,
    settings: Settings,
    age: int,
    same_site: Literal["lax", "strict"] = "strict",
) -> None:
    response.set_cookie(
        name,
        token,
        httponly=True,
        secure=settings.web_origin.startswith("https:"),
        samesite=same_site,
        path="/",
        max_age=age,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


def google_client(settings: Settings) -> Any:
    if not settings.google_client_id or not settings.google_client_secret.get_secret_value():
        raise HTTPException(503, "Google Sign-In is not configured")
    oauth = OAuth()
    return oauth.register(
        "google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret.get_secret_value(),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",
            "token_endpoint_auth_method": "client_secret_post",
            "timeout": 10,
            "trust_env": False,
            "follow_redirects": False,
        },
    )


def throttle(request: Request, action: str) -> None:
    # Peer identity only; do not trust forwarded headers. A dashboard bridge shares a
    # conservative aggregate limit. PostgreSQL makes it consistent across API processes.
    peer = request.client.host if request.client else "unknown"
    key = token_digest(action + ":" + peer)
    window = int(datetime.now(UTC).timestamp()) // 60
    with request.app.state.database.sessions.begin() as session:
        statement = insert(AuthenticationLimit).values(key=key, window=window, count=1)
        statement = statement.on_conflict_do_update(
            index_elements=[AuthenticationLimit.key],
            set_={
                "window": window,
                "count": case(
                    (AuthenticationLimit.window == window, AuthenticationLimit.count + 1), else_=1
                ),
            },
        )
        count = session.scalar(statement.returning(AuthenticationLimit.count))
        denied = count > request.app.state.settings.authentication_limit
        if denied:
            audit(session, "authentication_limited", outcome="denied")
    if denied:
        raise HTTPException(
            429, "Authentication temporarily unavailable", headers={"Retry-After": "60"}
        )


class LoginStart(BaseModel):
    invitation: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{43}$")


@router.post("/start")
async def start(payload: LoginStart, request: Request) -> RedirectResponse:
    origin_required(request)
    throttle(request, "start")
    settings: Settings = request.app.state.settings
    client = google_client(settings)
    browser, verifier, nonce = (
        secrets.token_urlsafe(32),
        secrets.token_urlsafe(64),
        secrets.token_urlsafe(32),
    )
    authorization = await client.create_authorization_url(
        settings.google_redirect_uri, code_verifier=verifier, nonce=nonce, prompt="select_account"
    )
    with request.app.state.database.sessions.begin() as session:
        invitation = (
            session.scalar(
                select(Invitation).where(Invitation.token_hash == token_digest(payload.invitation))
            )
            if payload.invitation
            else None
        )
        if payload.invitation and (
            invitation is None
            or invitation.revoked
            or invitation.used_by
            or invitation.expires_at <= datetime.now(UTC)
        ):
            audit(session, "login_failed", outcome="denied")
            response = RedirectResponse(settings.web_origin + "/?auth=denied", status_code=303)
            return response
        session.add(
            LoginTransaction(
                state_hash=token_digest(authorization["state"]),
                browser_hash=token_digest(browser),
                verifier=verifier,
                nonce=nonce,
                invitation_id=invitation.id if invitation else None,
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
    response = RedirectResponse(authorization["url"], status_code=303)
    cookie(response, LOGIN_COOKIE, browser, settings, 600, "lax")
    return response


def onboard(
    session: Session, claims: dict[str, Any], invitation_id: UUID | None, settings: Settings
) -> User:
    subject, email = claims.get("sub"), claims.get("email")
    if (
        not isinstance(subject, str)
        or not 1 <= len(subject) <= 255
        or claims.get("email_verified") is not True
    ):
        raise ValueError("Identity refused")
    if not isinstance(email, str) or "@" not in email or len(email) > 320:
        raise ValueError("Identity refused")
    # Serialize identity onboarding and bootstrap, including parallel callbacks.
    from sqlalchemy import text

    session.execute(text("SELECT pg_advisory_xact_lock(909001)"))
    identity = session.scalar(select(GoogleIdentity).where(GoogleIdentity.subject == subject))
    if identity is not None:
        user = session.get(User, identity.user_id, with_for_update=True)
        if user is None or not user.enabled:
            raise ValueError("Identity refused")
    else:
        # Never auto-link an existing local account by email. Local authority must
        # explicitly bind its UUID to a verified Google subject with the offline CLI.
        if session.scalar(select(User.id).where(func.lower(User.email) == email.lower())):
            raise ValueError("Identity refused")
        if invitation_id:
            invitation = session.get(Invitation, invitation_id, with_for_update=True)
        else:
            # A verified Google email may redeem its explicit administrator grant.
            # Never guess between conflicting pending invitations or link old users.
            pending = list(
                session.scalars(
                    select(Invitation)
                    .where(
                        func.lower(Invitation.email) == email.lower(),
                        Invitation.revoked.is_(False),
                        Invitation.used_by.is_(None),
                        Invitation.expires_at > datetime.now(UTC),
                    )
                    .limit(2)
                    .with_for_update()
                )
            )
            invitation = pending[0] if len(pending) == 1 else None
        bootstrap_state = session.get(AdministratorBootstrap, 1, with_for_update=True)
        if bootstrap_state is None:
            # Missing durable state is never permission to bootstrap again.
            raise ValueError("Identity refused")
        bootstrap = (
            bool(settings.google_bootstrap_email)
            and email.lower() == settings.google_bootstrap_email
            and (
                not settings.google_bootstrap_subject
                or subject == settings.google_bootstrap_subject
            )
            and bootstrap_state.closed_at is None
            and session.scalar(select(func.count()).select_from(GoogleIdentity)) == 0
            and session.scalar(
                select(func.count())
                .select_from(User)
                .where(or_(User.role == "platform_admin", User.roles.contains(["platform_admin"])))
            )
            == 0
        )
        if not bootstrap and (
            invitation is None
            or invitation.revoked
            or invitation.used_by
            or invitation.expires_at <= datetime.now(UTC)
            or invitation.email.lower() != email.lower()
        ):
            raise ValueError("Identity refused")
        if bootstrap:
            granted = ["platform_admin"]
        else:
            assert invitation is not None
            granted = invitation.roles
        user = User(email=email, display_name=email, role=granted[0], roles=granted)
        session.add(user)
        session.flush()
        session.add(GoogleIdentity(user_id=user.id, subject=subject))
        if invitation is not None:
            invitation.used_by = user.id
            audit(session, "invitation_accepted", user.id, invitation.id)
        if bootstrap:
            bootstrap_state.closed_at = datetime.now(UTC)
            bootstrap_state.founder_user_id = user.id
            audit(session, "administrator_bootstrapped", user.id, user.id)
    # Email is mutable display/contact data; identity lookup above uses only sub.
    user.email = email
    user.display_name = str(claims.get("name") or email)[:200]
    picture = claims.get("picture")
    user.picture = (
        picture
        if isinstance(picture, str) and picture.startswith("https://") and len(picture) <= 2048
        else None
    )
    return user


@router.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    throttle(request, "callback")
    settings: Settings = request.app.state.settings
    response = RedirectResponse(settings.web_origin + "/?auth=denied", status_code=303)
    cookie(response, LOGIN_COOKIE, "", settings, 0, "lax")
    state = request.query_params.get("state", "")
    browser = request.cookies.get(LOGIN_COOKIE, "")
    if (
        not state.isascii()
        or not browser.isascii()
        or not 1 <= len(state) <= 128
        or len(browser) != 43
    ):
        with request.app.state.database.sessions.begin() as session:
            audit(session, "login_failed", outcome="denied")
        return response
    with request.app.state.database.sessions.begin() as session:
        row = session.scalar(
            select(LoginTransaction)
            .where(
                LoginTransaction.state_hash == token_digest(state),
                LoginTransaction.browser_hash == token_digest(browser),
            )
            .with_for_update()
        )
        valid = row is not None and not row.consumed and row.expires_at > datetime.now(UTC)
        if not valid:
            audit(session, "login_failed", outcome="denied")
            return response
        row.consumed = True
        nonce, verifier, invitation_id = row.nonce, row.verifier, row.invitation_id
        row.nonce, row.verifier = "", ""
    # Consumption commits before provider I/O: errors and concurrent replays cannot
    # reuse a transaction, even across independent API processes.
    try:
        if (
            len(request.query_params.getlist("state")) != 1
            or len(request.query_params.getlist("code")) != 1
        ):
            raise ValueError("Invalid callback")
        client = google_client(settings)
        token = await client.fetch_access_token(
            redirect_uri=settings.google_redirect_uri,
            code_verifier=verifier,
            state=state,
            authorization_response=settings.google_redirect_uri
            + "?"
            + urlencode(list(request.query_params.multi_items())),
        )
        claims = await client.parse_id_token(
            token,
            nonce=nonce,
            leeway=30,
            claims_options={
                "iss": {
                    "essential": True,
                    "values": ["https://accounts.google.com", "accounts.google.com"],
                }
            },
        )
        if claims is None:
            raise ValueError("ID token required")
        with request.app.state.database.sessions.begin() as session:
            user = onboard(session, dict(claims), invitation_id, settings)
            secret = secrets.token_urlsafe(32)
            session.add(
                HumanSession(
                    owner_id=user.id,
                    token_hash=token_digest(secret),
                    expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_seconds),
                )
            )
            audit(session, "login", user.id, user.id)
        response = RedirectResponse(settings.web_origin + "/", status_code=303)
        cookie(response, LOGIN_COOKIE, "", settings, 0, "lax")
        cookie(response, SESSION_COOKIE, secret, settings, settings.session_seconds)
        return response
    except Exception:
        # Never expose provider errors, tokens, codes or identity claims in logs.
        with request.app.state.database.sessions.begin() as session:
            audit(session, "login_failed", outcome="denied")
        return response


@router.get("/me")
def me(request: Request, session: SessionDep) -> dict[str, object]:
    actor = human(request, session)
    user = session.get(User, actor.owner_id)
    assert user is not None
    return user_data(user)


@router.post("/logout")
def logout(request: Request, session: SessionDep) -> JSONResponse:
    actor = human(request, session)
    actor.revoked = True
    audit(session, "logout", actor.owner_id, actor.id)
    response = JSONResponse({"signed_out": True})
    cookie(response, SESSION_COOKIE, "", request.app.state.settings, 0)
    return response


@router.post("/sessions/revoke")
def revoke_sessions(request: Request, session: SessionDep) -> dict[str, bool]:
    actor = human(request, session)
    session.execute(
        update(HumanSession).where(HumanSession.owner_id == actor.owner_id).values(revoked=True)
    )
    audit(session, "sessions_revoked", actor.owner_id, actor.owner_id)
    return {"revoked": True}

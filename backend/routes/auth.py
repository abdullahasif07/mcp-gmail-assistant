from __future__ import annotations

import hmac
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2.rfc6749.errors import OAuth2Error

from auth_session import (
    clear_session_cookie,
    current_user_id,
    issue_session_cookie,
)
from config import settings
from db import delete_user, get_email, upsert_user

router = APIRouter()

# Short-lived cookie holding the OAuth `state` we sent to Google. Checking it
# on the callback prevents login CSRF (an attacker completing the flow with
# their own code and silently connecting *their* Gmail to the victim's
# browser). SameSite=Lax is enough: Google's redirect back is a top-level GET.
_STATE_COOKIE = "mm_oauth_state"
_STATE_TTL_SECONDS = 10 * 60

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _flow() -> Flow:
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
        autogenerate_code_verifier=False,
    )


@router.get("/login")
def login():
    flow = _flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        # Force Google to return a refresh_token every time. Without this,
        # Google only emits one on a user's very first consent, and you get
        # blank refresh_tokens on reconnect.
        prompt="consent",
    )
    resp = RedirectResponse(auth_url)
    resp.set_cookie(
        key=_STATE_COOKIE,
        value=state,
        max_age=_STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.is_prod,
        samesite="lax",
        path="/auth",
    )
    return resp


def _frontend_redirect(path: str, **params: str) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    resp = RedirectResponse(url=f"{settings.frontend_base_url}{path}{query}")
    resp.delete_cookie(_STATE_COOKIE, path="/auth")
    return resp


@router.get("/callback")
async def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    mm_oauth_state: str | None = Cookie(default=None),
):
    # User clicked "Cancel" on Google's consent screen (or Google refused).
    if error:
        return _frontend_redirect("/", auth_error=error)

    if not (code and state and mm_oauth_state) or not hmac.compare_digest(
        state, mm_oauth_state
    ):
        return _frontend_redirect("/", auth_error="invalid_state")

    flow = _flow()
    try:
        # fetch_token does blocking network I/O; keep it off the event loop.
        await run_in_threadpool(flow.fetch_token, code=code)
    except OAuth2Error as exc:
        return _frontend_redirect("/", auth_error=exc.error or "token_exchange_failed")
    creds = flow.credentials

    if not creds.refresh_token:
        raise HTTPException(
            status_code=400,
            detail=(
                "Google did not return a refresh token. Revoke Mailmind's "
                "access at https://myaccount.google.com/permissions and try "
                "again."
            ),
        )

    # Learn which Google account this is so we can key rows by email
    # instead of minting a fresh user_id on every reconnect.
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
        )
        r.raise_for_status()
        email = r.json().get("email")

    if not email:
        raise HTTPException(status_code=502, detail="Google did not return an email address")

    user_id = upsert_user(email=email, refresh_token=creds.refresh_token)

    resp = _frontend_redirect("/inbox")
    issue_session_cookie(resp, user_id)
    return resp


@router.get("/me")
def me(user_id: str = Depends(current_user_id)):
    return {"userId": user_id, "email": get_email(user_id)}


@router.post("/logout")
def logout(response: Response, user_id: str = Depends(current_user_id)):
    delete_user(user_id)
    clear_session_cookie(response)
    return {"ok": True}

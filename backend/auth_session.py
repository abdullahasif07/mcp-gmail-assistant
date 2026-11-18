"""Session handling.

The session cookie is a JWT with two claims that matter:

  * `mode` - "gmail" for a real Google account, "demo" for the sandboxed
    recruiter demo inbox. Tokens issued before demo mode existed have no
    `mode` claim and are treated as "gmail".
  * `sub`  - the user_id (gmail) or the demo session id (demo).

For gmail sessions the actual refresh token lives in SQLite (see db.py) and
is pulled on demand.

Why a JWT and not a random opaque token:
  * no extra DB round-trip just to resolve "is this cookie valid?"
  * rotating SESSION_JWT_SECRET instantly logs everyone out
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

import jwt
from fastapi import Cookie, HTTPException, Response

from config import settings

SessionMode = Literal["gmail", "demo"]

_SECRET = settings.session_jwt_secret

_ALG = "HS256"
_COOKIE_NAME = "mm_session"
_TTL_SECONDS: dict[SessionMode, int] = {
    "gmail": 60 * 60 * 24 * 30,  # 30 days
    "demo": 60 * 60 * 24,  # 1 day - demo mailboxes are throwaway
}

# In production (Vercel <-> Render = cross-site) the browser will only send
# the cookie back if it's SameSite=None; Secure. For local http://localhost
# dev, fall back to Lax so you don't need HTTPS to log in.
_COOKIE_SAMESITE = "none" if settings.is_prod else "lax"
_COOKIE_SECURE = settings.is_prod


@dataclass(frozen=True)
class Session:
    mode: SessionMode
    id: str

    @property
    def is_demo(self) -> bool:
        return self.mode == "demo"


def issue_session_cookie(resp: Response, subject: str, *, mode: SessionMode = "gmail") -> None:
    now = int(time.time())
    ttl = _TTL_SECONDS[mode]
    token = jwt.encode(
        {"sub": subject, "mode": mode, "iat": now, "exp": now + ttl},
        _SECRET,
        algorithm=_ALG,
    )
    resp.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=ttl,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        path="/",
    )


def clear_session_cookie(resp: Response) -> None:
    resp.delete_cookie(
        _COOKIE_NAME,
        path="/",
        samesite=_COOKIE_SAMESITE,
        secure=_COOKIE_SECURE,
    )


def _decode(token: str) -> Session | None:
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALG])
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    mode = payload.get("mode", "gmail")
    if not subject or mode not in _TTL_SECONDS:
        return None
    return Session(mode=mode, id=subject)


def current_session(mm_session: str | None = Cookie(default=None)) -> Session:
    """FastAPI dependency: 401 unless a valid session cookie is present."""
    if not mm_session:
        raise HTTPException(status_code=401, detail="Not signed in")
    session = _decode(mm_session)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid session")
    if session.is_demo and not settings.demo_enabled:
        raise HTTPException(status_code=401, detail="Demo mode is disabled")
    return session

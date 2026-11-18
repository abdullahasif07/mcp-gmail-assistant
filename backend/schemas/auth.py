"""Wire-format models for /auth endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MeResponse(BaseModel):
    userId: str
    email: str
    mode: Literal["gmail", "demo"]


class AuthOptions(BaseModel):
    """Which ways into the app the landing page should offer."""

    demo: bool
    demoAccessCodeRequired: bool
    gmail: bool


class DemoStartRequest(BaseModel):
    accessCode: str | None = Field(default=None, max_length=200)

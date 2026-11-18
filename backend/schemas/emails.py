"""Wire-format models for /emails endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SendEmailRequest(BaseModel):
    to: EmailStr
    subject: str = Field(..., min_length=1, max_length=998)
    body: str = Field(..., min_length=1)
    # Gmail message id being replied to. When set, the message is sent into
    # the same thread with proper In-Reply-To / References headers.
    inReplyTo: str | None = None


class SendEmailResponse(BaseModel):
    ok: bool = True
    detail: str


class EmailSummary(BaseModel):
    """One row in the inbox list. `from` is reserved in Python, so the
    field is named `sender` and aliased back to `from` on the wire."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    threadId: str | None = None
    sender: str = Field(..., alias="from")
    subject: str
    date: str


class EmailListResponse(BaseModel):
    query: str
    emails: list[EmailSummary]


class EmailDetail(EmailSummary):
    body: str

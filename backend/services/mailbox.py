"""Mailbox abstraction: one interface for real Gmail and the demo sandbox.

Routes and the chat loop depend on `current_mailbox` and never need to know
which mode the visitor is in:

    async with mailbox.session() as tools:
        text = await tools.call_tool("gmail_list_messages", {...})

* `GmailMailbox` opens an MCP session to the Node server with the user's
  refresh token (real Gmail).
* `DemoMailbox` (services/demo_mailbox.py) answers the same tools from an
  in-memory, pre-seeded fake inbox.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from fastapi import Depends, HTTPException

from auth_session import Session, current_session
from db import get_refresh_token
from services.demo_mailbox import demo_store
from services.mcp_service import mcp_session


class ToolCaller(Protocol):
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str: ...


class Mailbox(Protocol):
    def session(self) -> AbstractAsyncContextManager[ToolCaller]: ...


class GmailMailbox:
    def __init__(self, refresh_token: str) -> None:
        self._refresh_token = refresh_token

    def session(self) -> AbstractAsyncContextManager[ToolCaller]:
        return mcp_session(self._refresh_token)


async def call_tool(mailbox: Mailbox, tool_name: str, arguments: dict[str, Any]) -> str:
    """One-shot helper for routes that make a single tool call."""
    async with mailbox.session() as tools:
        return await tools.call_tool(tool_name, arguments)


def current_mailbox(session: Session = Depends(current_session)) -> Mailbox:
    """FastAPI dependency: the caller's mailbox (demo or real Gmail)."""
    if session.is_demo:
        return demo_store.get(session.id)
    token = get_refresh_token(session.id)
    if not token:
        # Row gone (logged out elsewhere, or the Fernet key was rotated).
        raise HTTPException(status_code=401, detail="Gmail connection missing")
    return GmailMailbox(token)

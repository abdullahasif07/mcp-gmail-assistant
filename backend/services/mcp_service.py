"""MCP client wrapper.

Spawns the Node MCP server (`mcp-server/index.js`) as a subprocess with the
*caller's* Gmail refresh token injected into its env, so every request acts
on the Gmail account of the user making it.

Spawning Node costs a few hundred ms, so callers that make several tool
calls in a row (the chat loop) should open one `mcp_session()` and reuse it
instead of calling `call_mcp_tool()` repeatedly.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ListToolsResult, TextContent

from config import settings

# Resolve relative to this file rather than the process CWD, so the backend
# works whether it's launched from backend/, the repo root, or Docker.
_SERVER_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent / "mcp-server" / "index.js"
)


class MCPToolError(RuntimeError):
    """Raised when an MCP tool reports failure (e.g. Gmail API error)."""


def _server_params(refresh_token: str) -> StdioServerParameters:
    return StdioServerParameters(
        command="node",
        args=[str(_SERVER_SCRIPT)],
        env={
            "GOOGLE_CLIENT_ID": settings.google_client_id,
            "GOOGLE_CLIENT_SECRET": settings.google_client_secret,
            "GOOGLE_REFRESH_TOKEN": refresh_token,
            # Node needs PATH to resolve itself + its deps when spawned.
            "PATH": os.environ.get("PATH", ""),
        },
    )


class MCPSession:
    """A connected MCP session bound to one user's Gmail credentials."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list_tools(self) -> ListToolsResult:
        return await self._session.list_tools()

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        result = await self._session.call_tool(tool_name, arguments)
        text = _result_text(result)
        if getattr(result, "is_error", False):
            raise MCPToolError(text or f"{tool_name} failed")
        return text


def _result_text(result: Any) -> str:
    if not isinstance(result, CallToolResult):
        return ""
    return "\n".join(c.text for c in result.content if isinstance(c, TextContent))


@asynccontextmanager
async def mcp_session(refresh_token: str) -> AsyncIterator[MCPSession]:
    try:
        async with (
            stdio_client(_server_params(refresh_token)) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            yield MCPSession(session)
    except BaseExceptionGroup as group:
        # stdio_client runs inside an anyio task group, which wraps anything
        # raised in the `with` body. Surface the real error so callers can
        # catch MCPToolError etc. directly.
        raise _unwrap(group) from None


def _unwrap(exc: BaseException) -> BaseException:
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


async def get_mcp_tools(refresh_token: str) -> ListToolsResult:
    async with mcp_session(refresh_token) as session:
        return await session.list_tools()


async def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    refresh_token: str,
) -> str:
    """One-shot helper: spawn the server, run one tool, shut it down."""
    async with mcp_session(refresh_token) as session:
        return await session.call_tool(tool_name, arguments)

"""OpenAI-driven chat that can call MCP tools (Gmail) as functions.

Uses the Chat Completions API with function tools. We run the tool loop
ourselves so every call is routed through the caller's mailbox (real Gmail
via the MCP stdio server, or the demo sandbox).

Deferred tools
--------------
`gmail_send_message` is intercepted: instead of being executed the model's
call is captured as a `pending_action` returned to the caller. The UI shows
it to the user for confirmation, then calls `execute_pending()` to actually
send. This avoids silent outbound mail from a chat prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import openai
from mcp import MCPError
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from config import settings
from services.mailbox import Mailbox, call_tool
from services.mcp_service import MCPToolError, get_mcp_tools

_MODEL = settings.openai_model
# The SDK retries transient failures (429/5xx/timeouts) with backoff itself.
_client = openai.AsyncOpenAI(api_key=settings.openai_api_key, max_retries=2, timeout=60)

# Tools that MUST NOT fire without explicit user confirmation.
DEFERRED_TOOLS: set[str] = {"gmail_send_message"}

_MAX_TOOL_ROUNDS = 6

SYSTEM_INSTRUCTION = (
    "You are Mailmind, an assistant for a personal Gmail inbox.\n"
    "You have tools to list, read, and send email and to fetch a whole thread.\n"
    "\n"
    "When to call which tool:\n"
    "- Listing mail: call gmail_list_messages with a sensible Gmail search query\n"
    "  (examples: 'is:unread', 'from:alice', 'newer_than:7d').\n"
    "- Reading one mail: call gmail_read_message with its message id.\n"
    "- Sending a NEW email (the user gives you a recipient and what to say,\n"
    "  e.g. 'email alice@x.com about lunch tomorrow'): call gmail_send_message\n"
    "  DIRECTLY with to/subject/body. Do NOT call gmail_list_messages or\n"
    "  gmail_read_message first - they are not needed for fresh outbound mail.\n"
    "- Replying: call gmail_read_message first for context (or gmail_get_thread\n"
    "  with its Thread id for the whole conversation), then call\n"
    "  gmail_send_message with replyToMessageId set to the original message id\n"
    "  and the same Subject prefixed by 'Re: ' if needed.\n"
    "\n"
    "Filling gmail_send_message arguments:\n"
    "- 'to' must be a single email address. If the user gave a name but no\n"
    "  address, ask them for the address instead of guessing.\n"
    "- If the user did not give a subject, write a short one (<=8 words) that\n"
    "  reflects the body. Never leave subject empty.\n"
    "- 'body' is the full message text the user wants to send. Add a brief\n"
    "  greeting and sign-off if the user did not include them.\n"
    "\n"
    "Confirmation contract (IMPORTANT):\n"
    "- gmail_send_message is NEVER actually sent by you. The system captures\n"
    "  it as a draft and the user will confirm in the UI.\n"
    "- After calling gmail_send_message ONCE, do NOT call it again in the same\n"
    "  turn even if the tool result mentions a draft. Just summarise what you\n"
    "  prepared (recipient + subject in one line) and ask the user to confirm.\n"
    "\n"
    "Style:\n"
    "- Keep chat replies under 6 short sentences unless asked for more."
)


@dataclass
class ChatResult:
    reply: str
    pending_action: dict | None = None  # {"tool": str, "args": dict}


def _clean_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Turn an MCP tool's JSON schema into OpenAI function `parameters`.

    OpenAI accepts standard JSON schema; we only drop the `$schema` marker
    and make sure the top level is an object."""
    if not schema:
        return {"type": "object", "properties": {}}
    cleaned = {k: v for k, v in schema.items() if k != "$schema"}
    cleaned.setdefault("type", "object")
    cleaned.setdefault("properties", {})
    return cleaned


# The MCP server's tool list is static, so fetch it once per process instead
# of on every chat turn. The Node server is the single source of truth for
# tool schemas - demo mode implements the same tools, so it reuses them.
_tool_cache: list[ChatCompletionToolParam] | None = None


async def _get_tools() -> list[ChatCompletionToolParam]:
    global _tool_cache
    if _tool_cache is None:
        # Listing tools never touches Gmail, so no refresh token is needed.
        listing = await get_mcp_tools(refresh_token="")
        _tool_cache = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": _clean_schema(tool.input_schema),
                },
            }
            for tool in listing.tools
        ]
    return _tool_cache


def friendly_ai_error(exc: BaseException) -> str | None:
    """Translate OpenAI errors into a short user-facing message."""
    if isinstance(exc, openai.RateLimitError):
        # OpenAI also uses 429 for "out of credits".
        if getattr(exc, "code", None) == "insufficient_quota":
            return "The AI provider account is out of credits. Please try again later."
        return "The AI provider is rate limiting requests. Wait a moment and try again."
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "OpenAI rejected the API key. Check OPENAI_API_KEY in backend/.env."
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return "Couldn't reach the AI provider. Please try again shortly."
    return None


def _deferred_response(tool_name: str, args: dict) -> str:
    """Synthetic tool result fed back to the model when we intercept a
    deferred tool call. Tells the model the action is pending user
    confirmation and must not be retried."""
    summary = ", ".join(f"{k}={v!r}" for k, v in args.items() if k != "body")
    return (
        f"The {tool_name} call has been captured as a draft and is pending user "
        "confirmation. Do NOT call it again. Summarise what you prepared "
        f"(fields: {summary or 'n/a'}) in one or two sentences and ask the user "
        "to confirm or edit."
    )


def _parse_args(raw: str | None) -> dict[str, Any] | None:
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    return args if isinstance(args, dict) else None


async def chat_once(message: str, mailbox: Mailbox) -> ChatResult:
    """Single-shot chat turn. Returns the model reply plus an optional
    pending action that the frontend must confirm before we actually run it.

    One mailbox session (for Gmail: one MCP server process) is kept open for
    the whole turn so multiple tool calls don't each pay the start-up cost."""
    tools = await _get_tools()
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": message},
    ]
    pending: dict | None = None
    reply: str | None = None

    async with mailbox.session() as session:
        for _ in range(_MAX_TOOL_ROUNDS + 1):
            completion = await _client.chat.completions.create(
                model=_MODEL, messages=messages, tools=tools
            )
            msg = completion.choices[0].message
            reply = msg.content
            calls = [c for c in (msg.tool_calls or []) if c.type == "function"]
            if not calls:
                break

            # Echo the assistant turn back with only input-valid fields
            # (a raw model_dump carries output-only keys like annotations).
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.function.name,
                                "arguments": c.function.arguments,
                            },
                        }
                        for c in calls
                    ],
                }
            )
            for call in calls:
                name = call.function.name
                args = _parse_args(call.function.arguments)
                if args is None:
                    result_text = f"Error: arguments for {name} were not valid JSON."
                elif name in DEFERRED_TOOLS:
                    pending = {"tool": name, "args": args}
                    result_text = _deferred_response(name, args)
                else:
                    try:
                        result_text = await session.call_tool(name, args)
                    except (MCPToolError, MCPError) as exc:
                        # Feed the failure back so the model can recover
                        # (e.g. bad message id) instead of failing the turn.
                        result_text = f"Error running {name}: {exc}"
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result_text}
                )

    text = reply or "I prepared the requested actions but didn't produce a text summary."
    return ChatResult(reply=text, pending_action=pending)


async def execute_pending(pending: dict, mailbox: Mailbox) -> str:
    """Run a previously-deferred tool call after the user has confirmed it."""
    tool = pending.get("tool")
    args = pending.get("args") or {}
    if tool not in DEFERRED_TOOLS:
        raise ValueError(f"{tool!r} is not a deferred tool")
    return await call_tool(mailbox, tool, args)


async def suggest_reply(email_text: str, instruction: str | None = None) -> str:
    """Generate a reply draft for one email. No tool calls - pure text in/out."""
    style = (
        f"\nStyle request: {instruction.strip()}"
        if instruction and instruction.strip()
        else ""
    )
    completion = await _client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You draft email replies on behalf of the user.\n"
                    "Write ONLY the reply body - no 'Subject:' line, no quoted original.\n"
                    "Match the tone of the sender. Keep it to 2-5 short sentences.\n"
                    "Include a greeting and a short sign-off." + style
                ),
            },
            {"role": "user", "content": f"--- ORIGINAL EMAIL ---\n{email_text}"},
        ],
    )
    return (completion.choices[0].message.content or "").strip()

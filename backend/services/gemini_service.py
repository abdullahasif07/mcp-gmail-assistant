"""Gemini-driven chat that can call MCP tools (Gmail) as functions.

Uses the `google-genai` SDK. Automatic function-calling is disabled so we can
route tool invocations through the MCP stdio client.

Deferred tools
--------------
`gmail_send_message` is intercepted: instead of being executed the model's
call is captured as a `pending_action` returned to the caller. The UI shows
it to the user for confirmation, then calls `execute_pending()` to actually
send. This avoids silent outbound mail from a chat prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from mcp import MCPError

from config import settings
from services.mailbox import Mailbox, call_tool
from services.mcp_service import MCPToolError, get_mcp_tools

_MODEL = settings.gemini_model
_client = genai.Client(api_key=settings.gemini_api_key)

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


def _strip_schema_for_gemini(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Gemini accepts OpenAPI-style JSON schema but rejects a few keys that
    MCP tools sometimes emit (`$schema`, `additionalProperties`, etc)."""
    if not schema:
        return {"type": "object", "properties": {}}
    drop = {"$schema", "additionalProperties", "title", "default"}

    def clean(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: clean(v) for k, v in node.items() if k not in drop}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    cleaned = clean(schema)
    cleaned.setdefault("type", "object")
    cleaned.setdefault("properties", {})
    return cleaned


# The MCP server's tool list is static, so fetch it once per process instead
# of on every chat turn. The Node server is the single source of truth for
# tool schemas - demo mode implements the same tools, so it reuses them.
_tool_cache: list[types.Tool] | None = None


async def _get_tools() -> list[types.Tool]:
    global _tool_cache
    if _tool_cache is None:
        # Listing tools never touches Gmail, so no refresh token is needed.
        listing = await get_mcp_tools(refresh_token="")
        declarations = [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters=_strip_schema_for_gemini(tool.input_schema),
            )
            for tool in listing.tools
        ]
        _tool_cache = [types.Tool(function_declarations=declarations)]
    return _tool_cache


def friendly_gemini_error(exc: BaseException) -> str | None:
    """Translate Gemini client errors into a short user-facing message."""
    if not isinstance(exc, genai_errors.ClientError):
        return None
    if exc.code == 429:
        return (
            "Gemini rate limit hit. Wait a bit, switch to a paid key, or set "
            "GEMINI_MODEL to a model with a higher quota."
        )
    if exc.code in (401, 403):
        return "Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env."
    return None


def _function_calls(response: types.GenerateContentResponse) -> list[types.FunctionCall]:
    if not response.candidates:
        return []
    content = response.candidates[0].content
    parts = (content.parts if content else None) or []
    return [p.function_call for p in parts if p.function_call]


def _deferred_response(tool_name: str, args: dict) -> str:
    """Synthetic tool result fed back to Gemini when we intercept a deferred
    tool call. Tells the model the action is pending user confirmation and
    must not be retried."""
    summary = ", ".join(f"{k}={v!r}" for k, v in args.items() if k != "body")
    return (
        f"The {tool_name} call has been captured as a draft and is pending user "
        "confirmation. Do NOT call it again. Summarise what you prepared "
        f"(fields: {summary or 'n/a'}) in one or two sentences and ask the user "
        "to confirm or edit."
    )


async def chat_once(message: str, mailbox: Mailbox) -> ChatResult:
    """Single-shot chat turn. Returns the model reply plus an optional
    pending action that the frontend must confirm before we actually run it.

    One mailbox session (for Gmail: one MCP server process) is kept open for
    the whole turn so multiple tool calls don't each pay the start-up cost."""
    tools = await _get_tools()
    async with mailbox.session() as session:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )
        chat = _client.aio.chats.create(model=_MODEL, config=config)

        response = await chat.send_message(message)
        pending: dict | None = None

        for _ in range(_MAX_TOOL_ROUNDS):
            calls = _function_calls(response)
            if not calls:
                break

            tool_responses: list[types.Part] = []
            for call in calls:
                name = call.name or ""
                args = dict(call.args) if call.args else {}
                if name in DEFERRED_TOOLS:
                    pending = {"tool": name, "args": args}
                    result_text = _deferred_response(name, args)
                else:
                    try:
                        result_text = await session.call_tool(name, args)
                    except (MCPToolError, MCPError) as exc:
                        # Feed the failure back so the model can recover
                        # (e.g. bad message id) instead of failing the turn.
                        result_text = f"Error running {name}: {exc}"
                tool_responses.append(
                    types.Part.from_function_response(
                        name=name,
                        response={"result": result_text},
                    )
                )

            response = await chat.send_message(tool_responses)

    text = response.text or (
        "I prepared the requested actions but didn't produce a text summary."
    )
    return ChatResult(reply=text, pending_action=pending)


async def execute_pending(pending: dict, mailbox: Mailbox) -> str:
    """Run a previously-deferred tool call after the user has confirmed it."""
    tool = pending.get("tool")
    args = pending.get("args") or {}
    if tool not in DEFERRED_TOOLS:
        raise ValueError(f"{tool!r} is not a deferred tool")
    return await call_tool(mailbox, tool, args)


async def suggest_reply(email_text: str, instruction: str | None = None) -> str:
    """Generate a reply draft for one email. No tool calls — pure text in/out."""
    tone = (
        f"\nStyle request: {instruction.strip()}"
        if instruction and instruction.strip()
        else ""
    )
    prompt = (
        "You are drafting a reply on behalf of the user.\n"
        "Write ONLY the reply body — no 'Subject:' line, no quoted original.\n"
        "Match the tone of the sender. Keep it to 2-5 short sentences.\n"
        "Include a greeting and a short sign-off."
        + tone
        + "\n\n--- ORIGINAL EMAIL ---\n"
        + email_text
    )
    response = await _client.aio.models.generate_content(
        model=_MODEL,
        contents=prompt,
    )
    return (response.text or "").strip()

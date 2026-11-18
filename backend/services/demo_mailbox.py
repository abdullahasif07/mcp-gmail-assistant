"""In-memory sandbox mailbox for the recruiter demo.

Implements the same four tools as the Node MCP server (list / read / send /
get thread) and returns text in exactly the same format, so the routes,
parsers and the Gemini tool loop work unchanged - they can't tell a demo
mailbox from a real Gmail one.

Each demo session gets its own copy of the seed data. "Sent" mail is only
appended to that session's Sent folder; nothing ever leaves the process.
Sessions live in memory: a restart simply hands visitors a freshly seeded
inbox.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime, parseaddr
from typing import Any

from services.demo_seed import DEMO_FROM, SEED_MESSAGES
from services.mcp_service import MCPToolError

_MAX_SESSIONS = 1000
_SESSION_IDLE_TTL = 24 * 60 * 60  # seconds


@dataclass
class DemoMessage:
    id: str
    thread_id: str
    sender: str
    to: str
    subject: str
    body: str
    date: datetime
    labels: set[str]
    unread: bool = False


# ── Gmail-style search ─────────────────────────────────────────────────────

# Optional leading "-" (negation), optional "operator:", then a quoted
# phrase or a bare word.
_TOKEN = re.compile(r'(-?)(?:(\w+):)?("[^"]*"|\S+)')
_RELATIVE = re.compile(r"^(\d+)([hdmy])$")
_UNIT_HOURS = {"h": 1, "d": 24, "m": 24 * 30, "y": 24 * 365}


def _relative_cutoff(value: str, now: datetime) -> datetime | None:
    m = _RELATIVE.match(value)
    if not m:
        return None
    return now - timedelta(hours=int(m.group(1)) * _UNIT_HOURS[m.group(2)])


def _absolute_date(value: str) -> datetime | None:
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _term_matches(msg: DemoMessage, op: str, value: str, now: datetime) -> bool:
    """Does one search term match? Unknown operators are ignored (match)."""
    haystack_from = msg.sender.lower()
    if op == "":
        text = f"{msg.sender} {msg.to} {msg.subject} {msg.body}".lower()
        return value in text
    if op == "from":
        return value in haystack_from
    if op == "to":
        return value in msg.to.lower()
    if op == "subject":
        return value in msg.subject.lower()
    if op == "is":
        if value == "unread":
            return msg.unread
        if value == "read":
            return not msg.unread
        return value in msg.labels
    if op in ("in", "label", "category"):
        if value in ("anywhere", "all"):
            return True
        return value in msg.labels
    if op in ("newer_than", "older_than"):
        cutoff = _relative_cutoff(value, now)
        if cutoff is None:
            return True
        return msg.date >= cutoff if op == "newer_than" else msg.date < cutoff
    if op in ("after", "before"):
        day = _absolute_date(value)
        if day is None:
            return True
        return msg.date >= day if op == "after" else msg.date < day
    # Demo messages have no attachments, so `has:` never matches; any other
    # unknown operator is ignored.
    return op != "has"


def matches(msg: DemoMessage, query: str, now: datetime) -> bool:
    """Evaluate a Gmail search query against one message.

    Terms are ANDed together (Gmail's default). `OR` and parentheses are
    tolerated but not modelled - good enough for the queries people and
    the model actually type.
    """
    for neg, op, raw in _TOKEN.findall(query or ""):
        value = raw.strip('"()').lower()
        if not value or (not op and value in ("or", "and")):
            continue
        ok = _term_matches(msg, op.lower(), value, now)
        if ok == bool(neg):
            return False
    return True


# ── Output formatting (mirrors mcp-server/index.js) ────────────────────────


def _rfc2822(dt: datetime) -> str:
    return format_datetime(dt)


def _list_entry(msg: DemoMessage) -> str:
    return (
        f"ID: {msg.id}\nThread: {msg.thread_id}\nFrom: {msg.sender}\n"
        f"Subject: {msg.subject}\nDate: {_rfc2822(msg.date)}"
    )


def _read_text(msg: DemoMessage) -> str:
    return (
        f"From: {msg.sender}\nDate: {_rfc2822(msg.date)}\nSubject: {msg.subject}\n"
        f"Thread: {msg.thread_id}\n\nBody:\n{msg.body}"
    )


def _thread_entry(msg: DemoMessage) -> str:
    return (
        f"ID: {msg.id}\nFrom: {msg.sender}\nDate: {_rfc2822(msg.date)}\n"
        f"Subject: {msg.subject}\n\n{msg.body}"
    )


# ── Mailbox ────────────────────────────────────────────────────────────────


@dataclass
class DemoMailbox:
    messages: list[DemoMessage]
    ai_calls: int = 0
    last_seen: float = field(default_factory=time.monotonic)
    _counter: int = 0

    @classmethod
    def seeded(cls, now: datetime | None = None) -> DemoMailbox:
        now = now or datetime.now(UTC)
        messages = [
            DemoMessage(
                id=m["id"],
                thread_id=m["thread"],
                sender=m["from"],
                to=m["to"],
                subject=m["subject"],
                body=m["body"],
                date=(now - timedelta(minutes=m["age"])).replace(microsecond=0),
                labels=set(m["labels"]),
                unread=m["unread"],
            )
            for m in SEED_MESSAGES
        ]
        return cls(messages=messages)

    # Same shape as a Mailbox / MCP session (see services/mailbox.py).
    @asynccontextmanager
    async def session(self) -> AsyncIterator[DemoMailbox]:
        yield self

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        handlers = {
            "gmail_list_messages": self._list,
            "gmail_read_message": self._read,
            "gmail_send_message": self._send,
            "gmail_get_thread": self._thread,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            raise MCPToolError(f"Unknown tool: {tool_name}")
        try:
            return handler(**arguments)
        except TypeError as exc:  # missing / unexpected arguments
            raise MCPToolError(f"Invalid arguments for {tool_name}: {exc}") from None

    def _get(self, message_id: str) -> DemoMessage:
        for msg in self.messages:
            if msg.id == message_id:
                return msg
        raise MCPToolError("Requested entity was not found.")

    def _list(self, query: str = "in:inbox", maxResults: float = 5) -> str:
        now = datetime.now(UTC)
        limit = max(1, min(int(maxResults), 50))
        found = sorted(
            (m for m in self.messages if matches(m, query, now)),
            key=lambda m: m.date,
            reverse=True,
        )[:limit]
        if not found:
            return "No emails found."
        return "\n\n---\n\n".join(_list_entry(m) for m in found)

    def _read(self, messageId: str) -> str:
        return _read_text(self._get(messageId))

    def _send(
        self,
        to: str,
        subject: str,
        body: str,
        replyToMessageId: str | None = None,
    ) -> str:
        if not parseaddr(to)[1]:
            raise MCPToolError(f"Invalid recipient address: {to!r}")
        thread_id = self._get(replyToMessageId).thread_id if replyToMessageId else None
        self._counter += 1
        msg_id = f"sent-{self._counter}"
        self.messages.append(
            DemoMessage(
                id=msg_id,
                thread_id=thread_id or f"t-{msg_id}",
                sender=DEMO_FROM,
                to=to,
                subject=subject,
                body=body,
                date=datetime.now(UTC).replace(microsecond=0),
                labels={"sent"},
            )
        )
        return (
            f"Demo mode: email to {to} saved to Sent. "
            "It was not actually delivered."
        )

    def _thread(self, threadId: str) -> str:
        msgs = sorted(
            (m for m in self.messages if m.thread_id == threadId),
            key=lambda m: m.date,
        )
        if not msgs:
            raise MCPToolError("Requested entity was not found.")
        return "\n\n---\n\n".join(_thread_entry(m) for m in msgs)


class DemoStore:
    """Per-session demo mailboxes with an LRU cap and idle expiry."""

    def __init__(self) -> None:
        self._boxes: OrderedDict[str, DemoMailbox] = OrderedDict()
        self._lock = threading.Lock()

    def create(self) -> str:
        session_id = f"demo-{uuid.uuid4().hex}"
        with self._lock:
            self._boxes[session_id] = DemoMailbox.seeded()
            self._evict()
        return session_id

    def get(self, session_id: str) -> DemoMailbox:
        """Return the session's mailbox, re-seeding one if it was evicted or
        the server restarted - the visitor just sees a fresh demo inbox."""
        with self._lock:
            box = self._boxes.get(session_id)
            if box is None:
                box = DemoMailbox.seeded()
                self._boxes[session_id] = box
                self._evict()
            else:
                self._boxes.move_to_end(session_id)
            box.last_seen = time.monotonic()
            return box

    def discard(self, session_id: str) -> None:
        with self._lock:
            self._boxes.pop(session_id, None)

    def _evict(self) -> None:
        cutoff = time.monotonic() - _SESSION_IDLE_TTL
        for sid in [s for s, b in self._boxes.items() if b.last_seen < cutoff]:
            del self._boxes[sid]
        while len(self._boxes) > _MAX_SESSIONS:
            self._boxes.popitem(last=False)


demo_store = DemoStore()

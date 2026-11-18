"""Per-session chat memory.

Keeps each visitor's recent conversation so follow-ups like "yes, send it"
or "make it shorter" work. Two views are stored:

* `messages`   - the OpenAI message list (user / assistant / tool calls /
                 tool results) replayed to the model on the next turn.
* `transcript` - just the user-visible text, so the UI can restore the
                 chat panel after a page reload.

To keep the AI bill bounded, only the last few user turns are replayed and
tool results from earlier turns (email bodies, listings) are truncated.
Memory lives in process and is lost on restart - fine for this app.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

_MAX_TURNS = 8  # user messages replayed to the model
_MAX_TRANSCRIPT = 40  # chat bubbles kept for the UI
_OLD_TOOL_RESULT_CHARS = 1500
_MAX_CONVERSATIONS = 1000
_IDLE_TTL = 24 * 60 * 60  # seconds


@dataclass
class Conversation:
    messages: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[dict[str, str]] = field(default_factory=list)
    # The draft most recently shown to the user, if they haven't acted on it.
    pending: dict[str, Any] | None = None
    last_seen: float = field(default_factory=time.monotonic)

    def add_turn(self, turn_messages: list[dict[str, Any]], user_text: str, reply: str) -> None:
        self.messages = _trim(self.messages + turn_messages)
        self.note(user_text, role="user")
        self.note(reply, role="assistant")

    def note(self, text: str, *, role: str) -> None:
        self.transcript.append({"role": role, "text": text})
        del self.transcript[:-_MAX_TRANSCRIPT]

    def record_assistant(self, text: str) -> None:
        """Tell the model (and the UI) about something that happened outside
        the chat, e.g. the user clicking Confirm & send."""
        self.messages = _trim([*self.messages, {"role": "assistant", "content": text}])
        self.note(text, role="assistant")


def _trim(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last _MAX_TURNS user turns; shorten older tool results.

    Cutting at a user message keeps assistant tool calls and their tool
    results together, which the API requires."""
    user_idx = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_idx) > _MAX_TURNS:
        messages = messages[user_idx[-_MAX_TURNS] :]
        user_idx = [i for i, m in enumerate(messages) if m.get("role") == "user"]

    latest_turn = user_idx[-1] if user_idx else 0
    trimmed = []
    for i, m in enumerate(messages):
        content = m.get("content")
        if (
            i < latest_turn
            and m.get("role") == "tool"
            and isinstance(content, str)
            and len(content) > _OLD_TOOL_RESULT_CHARS
        ):
            m = {**m, "content": content[:_OLD_TOOL_RESULT_CHARS] + "\n[...truncated]"}
        trimmed.append(m)
    return trimmed


class ChatMemory:
    def __init__(self) -> None:
        self._convs: OrderedDict[str, Conversation] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Conversation:
        with self._lock:
            conv = self._convs.get(key)
            if conv is None:
                conv = self._convs[key] = Conversation()
            else:
                self._convs.move_to_end(key)
            conv.last_seen = time.monotonic()
            self._evict()
            return conv

    def clear(self, key: str) -> None:
        with self._lock:
            self._convs.pop(key, None)

    def _evict(self) -> None:
        cutoff = time.monotonic() - _IDLE_TTL
        for key in [k for k, c in self._convs.items() if c.last_seen < cutoff]:
            del self._convs[key]
        while len(self._convs) > _MAX_CONVERSATIONS:
            self._convs.popitem(last=False)


chat_memory = ChatMemory()

"""Cheap in-memory guards that keep a public deployment's AI bill bounded.

* A global daily cap on AI requests (`AI_DAILY_LIMIT`).
* A per-session cap for demo visitors (`DEMO_SESSION_AI_LIMIT`).
* A per-IP limiter for demo access-code attempts (brute-force protection).

Counters live in process memory, so they reset on restart. That's fine for a
single-instance portfolio deployment; also set a hard spending limit with
your AI provider as the last line of defence.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from fastapi import Depends, HTTPException

from auth_session import Session, current_session
from config import settings
from services.demo_mailbox import demo_store


class DailyCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = ""
        self._count = 0

    def try_consume(self, limit: int) -> bool:
        """Count one request; False if today's limit is already reached."""
        if limit <= 0:
            return True
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        with self._lock:
            if today != self._day:
                self._day, self._count = today, 0
            if self._count >= limit:
                return False
            self._count += 1
            return True


class SlidingWindowLimiter:
    def __init__(self, max_hits: int, window_seconds: float) -> None:
        self._max = max_hits
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self._window:
                hits.popleft()
            if len(hits) >= self._max:
                return False
            hits.append(now)
            return True


daily_ai_requests = DailyCounter()
demo_code_attempts = SlidingWindowLimiter(max_hits=10, window_seconds=10 * 60)


def ai_budget(session: Session = Depends(current_session)) -> None:
    """FastAPI dependency for every endpoint that calls the AI model."""
    if session.is_demo:
        box = demo_store.get(session.id)
        if box.ai_calls >= settings.demo_session_ai_limit:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"This demo session has used its {settings.demo_session_ai_limit} "
                    "AI requests. Exit and restart the demo to keep exploring."
                ),
            )
    if not daily_ai_requests.try_consume(settings.ai_daily_limit):
        raise HTTPException(
            status_code=429,
            detail="The app's daily AI budget is used up. Please try again tomorrow.",
        )
    if session.is_demo:
        box.ai_calls += 1

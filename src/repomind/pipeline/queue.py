"""Job worker with bounded retries, exponential backoff, and a dead-letter
queue. A job that exhausts its retries is moved to the DLQ (never dropped) so an
operator can inspect and replay it. This is a core correctness guarantee.
"""
from __future__ import annotations

import time
from typing import Callable

from repomind.state import StateStore


class Worker:
    def __init__(
        self,
        handler: Callable[[dict], None],
        state: StateStore,
        max_retries: int = 5,
        backoff: str = "exponential",
        base_delay: float = 0.5,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.handler = handler
        self.state = state
        self.max_retries = max_retries
        self.backoff = backoff
        self.base_delay = base_delay
        self.sleeper = sleeper

    def _delay(self, attempt: int) -> float:
        if self.backoff == "exponential":
            return self.base_delay * (2 ** attempt)
        return self.base_delay

    def process(self, job: dict) -> bool:
        """Run a job with retries. Returns True on success, False if dead-lettered."""
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                self.handler(job)
                return True
            except Exception as exc:
                last_err = exc
                if attempt < self.max_retries - 1:
                    self.sleeper(self._delay(attempt))
        self.state.add_dead_letter(job, repr(last_err))
        return False

    def replay_dead_letters(self) -> tuple[int, int]:
        """Re-attempt every dead-lettered job. Returns (replayed_ok, still_failing)."""
        ok = 0
        fail = 0
        for dl in self.state.list_dead_letters():
            try:
                self.handler(dl["job"])
                self.state.remove_dead_letter(dl["id"])
                ok += 1
            except Exception:
                fail += 1
        return ok, fail

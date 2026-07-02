"""Authentication and rate limiting.

Supports MULTIPLE named API keys, each with scopes, plus a per-key rate limit.

Scopes (hierarchical): admin > write > read.
  - read  : query/read endpoints (/health, /ask, /graph)
  - write : ingestion + sync (/ingest/message, /sync, /verify)
  - admin : destructive ops (/forget) and implies all others

Key secrets always come from the environment (each key names its own env var),
never from the config file. The legacy single token (api.token_env) is treated
as an admin key named "default" for backward compatibility.
"""
from __future__ import annotations

import hmac
import os
import time
from dataclasses import dataclass
from typing import Callable

SCOPES = ("read", "write", "admin")


@dataclass(frozen=True)
class ApiKey:
    name: str
    token: str
    scopes: tuple[str, ...]


def has_scope(key: ApiKey, required: str) -> bool:
    """Hierarchical scope check: admin implies write implies read."""
    if "admin" in key.scopes:
        return True
    if required == "read" and "write" in key.scopes:
        return True
    return required in key.scopes


class KeyRegistry:
    """Holds the active API keys and matches a provided token in constant time."""

    def __init__(self, keys: list[ApiKey]) -> None:
        self._keys = keys

    @property
    def empty(self) -> bool:
        return not self._keys

    def names(self) -> list[str]:
        return [k.name for k in self._keys]

    def match(self, provided: str | None) -> ApiKey | None:
        if not provided:
            return None
        for key in self._keys:
            # Constant-time compare against every key (avoids timing oracle).
            if hmac.compare_digest(provided, key.token):
                return key
        return None


def build_registry(config) -> KeyRegistry:
    """Assemble the key registry from config + environment.

    - The legacy single token (api.token_env) becomes an admin key "default".
    - Each api.keys[] entry reads its own token_env; missing env -> skipped.
    - Duplicate names are de-duplicated (first wins) to avoid ambiguity.
    """
    keys: list[ApiKey] = []
    seen_names: set[str] = set()

    legacy = os.environ.get(config.api.token_env)
    if legacy:
        keys.append(ApiKey("default", legacy, ("admin",)))
        seen_names.add("default")

    for kc in config.api.keys:
        if kc.name in seen_names:
            continue
        token = os.environ.get(kc.token_env)
        if not token:
            continue  # key defined but its secret is not set -> inactive
        scopes = tuple(s for s in kc.scopes if s in SCOPES) or ("read",)
        keys.append(ApiKey(kc.name, token, scopes))
        seen_names.add(kc.name)

    return KeyRegistry(keys)


class RateLimiter:
    """Fixed-window per-key rate limiter (in-process).

    Note: in-process counters are correct for a single worker. For multiple
    workers behind a load balancer, a shared store (e.g. Redis) would be needed;
    that is noted as future work.
    """

    def __init__(
        self, limit: int, window_seconds: int, now: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._now = now
        self._state: dict[str, tuple[float, int]] = {}

    @property
    def enabled(self) -> bool:
        return self.limit > 0 and self.window > 0

    def check(self, key_name: str) -> tuple[bool, int]:
        """Record a request. Returns (allowed, retry_after_seconds)."""
        if not self.enabled:
            return True, 0
        now = self._now()
        start, count = self._state.get(key_name, (now, 0))
        if now - start >= self.window:
            start, count = now, 0  # window rolled over
        count += 1
        self._state[key_name] = (start, count)
        if count > self.limit:
            retry_after = int(self.window - (now - start)) + 1
            return False, max(retry_after, 1)
        return True, 0


def build_rate_limiter(config) -> RateLimiter:
    from repomind.config import parse_interval_seconds

    window = parse_interval_seconds(config.api.rate_window) if config.api.rate_window else 0
    return RateLimiter(config.api.rate_limit, window)

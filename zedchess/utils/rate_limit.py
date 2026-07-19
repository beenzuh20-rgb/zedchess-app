"""
Rate limiting + brute-force protection.

A lightweight, in-memory fixed-window limiter keyed by an arbitrary string
(e.g. IP, or ``"login:<ip>"``). Good enough for a single-process dev server;
swap for Redis in a multi-worker production deployment without changing the
call sites (see ``RateLimiter.limit`` signature).
"""

import time
from collections import defaultdict


class RateLimiter:
    """Fixed-window rate limiter kept in process memory."""

    def __init__(self) -> None:
        # key -> list of timestamps
        self._hits: dict[str, list[float]] = defaultdict(list)

    def limit(self, key: str, max_hits: int, window: int) -> bool:
        """Return ``True`` if the request is allowed (under the limit)."""
        now = time.time()
        hits = self._hits[key]
        # Drop outdated timestamps.
        self._hits[key] = [t for t in hits if now - t < window]
        if len(self._hits[key]) >= max_hits:
            return False
        self._hits[key].append(now)
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


# Process-wide shared limiter.
limiter = RateLimiter()


def client_ip() -> str:
    """Best-effort client IP behind proxies (X-Forwarded-For first hop)."""
    from flask import request

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"

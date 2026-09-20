"""Server-side rate limiting (PLAN.md §6).

In-process, in-memory sliding windows. This is deliberate for v1: the real
defense against abuse is the mirrored Cloudflare rule at the edge, which stops
traffic before it reaches the Pi at all. This layer exists so the API is still
correct when reached directly over the tailnet, and so a runaway client (a retry
loop in the outbox, say) cannot hammer the database.

Consequence worth knowing: counters reset when the container restarts.
"""
import math
import threading
import time
from collections import defaultdict, deque
from typing import NamedTuple

from . import config


class Refusal(NamedTuple):
    """Why a write was refused, and how long until it would not be.

    The window is a sliding one, so the answer is exact: a slot frees when the
    oldest attempt inside the window ages out of it. Clients pace themselves on
    this (`Retry-After`) instead of guessing, which is what stops a bulk import
    from crawling behind a 20-second poll.
    """

    reason: str
    retry_after: int


_lock = threading.Lock()
_writes: dict[str, deque[float]] = defaultdict(deque)
_failed_auth: dict[str, deque[float]] = defaultdict(deque)

MINUTE = 60.0
DAY = 86_400.0


def _prune(bucket: deque[float], window: float, now: float) -> None:
    cutoff = now - window
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def _seconds_until(t: float, window: float, now: float) -> int:
    """Whole seconds until `t` leaves `window`; never less than one."""
    return max(1, math.ceil(t + window - now))


def check_write(player_id: str, now: float | None = None) -> Refusal | None:
    """Record a write attempt. Returns None if allowed, else a Refusal.

    The attempt is only recorded when it is allowed, so a client being throttled
    does not extend its own penalty by continuing to retry.
    """
    now = time.time() if now is None else now
    with _lock:
        bucket = _writes[player_id]
        _prune(bucket, DAY, now)
        in_minute = [t for t in bucket if t >= now - MINUTE]
        if len(in_minute) >= config.WRITES_PER_MIN:
            return Refusal(
                f"write rate limit: {config.WRITES_PER_MIN}/min",
                _seconds_until(in_minute[0], MINUTE, now),
            )
        if len(bucket) >= config.WRITES_PER_DAY:
            return Refusal(
                f"write rate limit: {config.WRITES_PER_DAY}/day",
                _seconds_until(bucket[0], DAY, now),
            )
        bucket.append(now)
        return None


def record_failed_auth(ip: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _lock:
        bucket = _failed_auth[ip]
        _prune(bucket, MINUTE, now)
        bucket.append(now)


def failed_auth_exceeded(ip: str, now: float | None = None) -> Refusal | None:
    """None while the caller may still try; a Refusal once they may not."""
    now = time.time() if now is None else now
    with _lock:
        bucket = _failed_auth[ip]
        _prune(bucket, MINUTE, now)
        if len(bucket) < config.FAILED_AUTH_PER_MIN:
            return None
        return Refusal(
            "too many failed authentications",
            _seconds_until(bucket[0], MINUTE, now),
        )


def reset() -> None:
    """Test hook."""
    with _lock:
        _writes.clear()
        _failed_auth.clear()

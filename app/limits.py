"""Server-side rate limiting (PLAN.md §6).

In-process, in-memory sliding windows. This is deliberate for v1: the real
defense against abuse is the mirrored Cloudflare rule at the edge, which stops
traffic before it reaches the Pi at all. This layer exists so the API is still
correct when reached directly over the tailnet, and so a runaway client (a retry
loop in the outbox, say) cannot hammer the database.

Consequence worth knowing: counters reset when the container restarts.
"""
import threading
import time
from collections import defaultdict, deque

from . import config

_lock = threading.Lock()
_writes: dict[str, deque[float]] = defaultdict(deque)
_failed_auth: dict[str, deque[float]] = defaultdict(deque)

MINUTE = 60.0
DAY = 86_400.0


def _prune(bucket: deque[float], window: float, now: float) -> None:
    cutoff = now - window
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def check_write(player_id: str, now: float | None = None) -> str | None:
    """Record a write attempt. Returns None if allowed, else a reason string.

    The attempt is only recorded when it is allowed, so a client being throttled
    does not extend its own penalty by continuing to retry.
    """
    now = time.time() if now is None else now
    with _lock:
        bucket = _writes[player_id]
        _prune(bucket, DAY, now)
        per_min = sum(1 for t in bucket if t >= now - MINUTE)
        if per_min >= config.WRITES_PER_MIN:
            return f"write rate limit: {config.WRITES_PER_MIN}/min"
        if len(bucket) >= config.WRITES_PER_DAY:
            return f"write rate limit: {config.WRITES_PER_DAY}/day"
        bucket.append(now)
        return None


def record_failed_auth(ip: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _lock:
        bucket = _failed_auth[ip]
        _prune(bucket, MINUTE, now)
        bucket.append(now)


def failed_auth_exceeded(ip: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    with _lock:
        bucket = _failed_auth[ip]
        _prune(bucket, MINUTE, now)
        return len(bucket) >= config.FAILED_AUTH_PER_MIN


def reset() -> None:
    """Test hook."""
    with _lock:
        _writes.clear()
        _failed_auth.clear()

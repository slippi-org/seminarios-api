"""Shared FastAPI dependencies."""
import sqlite3

from fastapi import Depends, HTTPException, Request

from . import auth, db, limits


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def client_ip(request: Request) -> str:
    """Best-effort caller IP for the failed-auth limiter.

    The only public path in is the Cloudflare tunnel, which sets
    CF-Connecting-IP. Over the tailnet these headers are spoofable, but the worst
    a spoofer achieves is spreading their own failed attempts across buckets --
    they cannot use it to raise anyone else's limit.
    """
    for header in ("cf-connecting-ip", "x-forwarded-for"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def current_player(
    request: Request, conn: sqlite3.Connection = Depends(get_conn)
) -> sqlite3.Row:
    ip = client_ip(request)
    locked_out = limits.failed_auth_exceeded(ip)
    if locked_out:
        raise HTTPException(429, locked_out.reason, headers=_retry_after(locked_out))

    token = auth.bearer_from_header(request.headers.get("authorization"))
    player = auth.lookup(conn, token)
    if player is None:
        limits.record_failed_auth(ip)
        raise HTTPException(401, "invalid or missing token")
    return player


def guard_write(player: sqlite3.Row) -> None:
    refusal = limits.check_write(player["id"])
    if refusal:
        raise HTTPException(429, refusal.reason, headers=_retry_after(refusal))


def _retry_after(refusal: limits.Refusal) -> dict[str, str]:
    """A 429 that does not say when to come back makes every client guess.

    Browsers cannot read this header cross-origin unless it is exposed, which
    `main.py` does; the outbox in `seminarios/app.js` paces its flush on it.
    """
    return {"Retry-After": str(refusal.retry_after)}

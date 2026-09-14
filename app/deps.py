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
    if limits.failed_auth_exceeded(ip):
        raise HTTPException(429, "too many failed authentications")

    token = auth.bearer_from_header(request.headers.get("authorization"))
    player = auth.lookup(conn, token)
    if player is None:
        limits.record_failed_auth(ip)
        raise HTTPException(401, "invalid or missing token")
    return player


def guard_write(player: sqlite3.Row) -> None:
    reason = limits.check_write(player["id"])
    if reason:
        raise HTTPException(429, reason)

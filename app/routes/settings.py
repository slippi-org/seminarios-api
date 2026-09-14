"""Shared campaign settings (PLAN.md §5).

`era`, `campaignStart` and especially `today` are campaign-wide facts. Kept
per-browser, the party silently disagrees about what day it is.
"""
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import access, config, store
from ..db import utcnow
from ..deps import current_player, get_conn, guard_write
from ..models import SettingsPut

router = APIRouter()


@router.get("/settings")
def get_settings(
    scope: str = Query(default=config.DEFAULT_SCOPE),
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    return {"scope": scope, "settings": store.read_settings(conn, scope),
            "server_time": utcnow(conn)}


@router.put("/settings")
def put_settings(
    body: SettingsPut,
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Partial: only the keys present are written."""
    guard_write(player)
    if not access.may_write_settings(player["role"]):
        raise HTTPException(403, "only a gm may change campaign settings")

    fields = body.model_dump(exclude_unset=True)
    fields.pop("scope", None)
    now = utcnow(conn)
    for key, value in fields.items():
        conn.execute(
            "INSERT INTO campaign_settings (scope, key, value, updated_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(scope, key) DO UPDATE SET value = excluded.value,"
            "   updated_at = excluded.updated_at",
            (body.scope, key, json.dumps(value), now),
        )
    conn.commit()
    return {"scope": body.scope, "settings": store.read_settings(conn, body.scope),
            "server_time": now}

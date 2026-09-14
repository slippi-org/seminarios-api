import sqlite3

from fastapi import APIRouter, Depends, Query

from .. import config, store
from ..db import utcnow
from ..deps import current_player, get_conn

router = APIRouter()


@router.get("/state")
def get_state(
    since: str | None = Query(default=None),
    scope: str = Query(default=config.DEFAULT_SCOPE),
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Delta sync. Omit `since` for a full load.

    `server_time` is read BEFORE the rows so that a client which stores it and
    passes it back as `since` cannot miss a write committed mid-request.
    """
    now = utcnow(conn)
    role = player["role"]
    return {
        "events": store.fetch_visible(conn, "events", scope, role, since),
        "notes": store.fetch_visible(conn, "notes", scope, role, since),
        "settings": store.read_settings(conn, scope),
        "server_time": now,
    }

import sqlite3

from fastapi import APIRouter, Depends

from .. import store
from ..db import utcnow
from ..deps import current_player, get_conn

router = APIRouter()


@router.get("/me")
def me(
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Also the token-validity check the frontend runs on page load."""
    return {
        "player": {
            "id": player["id"],
            "display_name": player["display_name"],
            "role": player["role"],
            "created_at": player["created_at"],
        },
        "role": player["role"],
        "characters": store.characters_of(conn, player["id"]),
        "server_time": utcnow(conn),
    }

import sqlite3

from fastapi import APIRouter, Depends

from .. import store
from ..deps import current_player, get_conn

router = APIRouter()


@router.get("/roster")
def roster(
    _: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Who everyone is, for any authenticated caller (PLAN.md §6, known gap).

    Events carry bare author_id / character_id; this is how the frontend turns
    them into a name and a colour, and how the GM finds an NPC another player
    owns. Never role-filtered: there is nothing secret in a name.

    Inactive rows are included, flagged, rather than dropped: a player who has
    left still authored their entries, and a memorial must not forget who.
    Pickers should offer `active` rows only.
    """
    return {
        "players": store.all_players(conn),
        "characters": store.all_characters(conn),
    }

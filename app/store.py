"""Row queries and serialization shared by the routes."""
import sqlite3

from . import access

# The frontend's CAL.timesOfDay order. Sorting the raw column would give
# alphabetical -- afternoon, evening, midday, morning, night -- which is wrong.
TIME_RANK = """CASE time_of_day
                 WHEN 'morning'   THEN 0
                 WHEN 'midday'    THEN 1
                 WHEN 'afternoon' THEN 2
                 WHEN 'evening'   THEN 3
                 WHEN 'night'     THEN 4
                 ELSE 5 END"""

# PLAN.md §5: created_at replaces the frontend's client-set `timestamp` as the
# tiebreaker within a (day, time_of_day), so it must be on the wire.
EVENT_ORDER = f"ORDER BY day, {TIME_RANK}, created_at, id"
NOTE_ORDER = "ORDER BY created_at, id"

EVENT_COLS = (
    "id, scope, place_id, place, day, time_of_day, text, author_id, "
    "character_id, visibility, created_at, updated_at, deleted_at"
)
NOTE_COLS = (
    "id, scope, place_id, text, author_id, visibility, "
    "created_at, updated_at, deleted_at"
)


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def fetch_visible(
    conn: sqlite3.Connection,
    table: str,
    scope: str,
    role: str | None,
    since: str | None,
) -> list[dict]:
    """Rows in `scope` that `role` may read.

    With `since`, returns everything touched after that instant **including
    tombstones**, so a client learns about deletions it missed. Without it,
    returns the live set only -- a first load has no use for graves.
    """
    cols = EVENT_COLS if table == "events" else NOTE_COLS
    order = EVENT_ORDER if table == "events" else NOTE_ORDER
    vis_sql, vis_params = access.visible_to(role)

    sql = f"SELECT {cols} FROM {table} WHERE scope = ? AND ({vis_sql})"
    params: list = [scope, *vis_params]
    if since is not None:
        # Inclusive (>=), not exclusive. `since` is a server_time the client read
        # BEFORE these rows were selected, so a row written in that same
        # millisecond is still in flight; ">" would drop it permanently. ">="
        # re-sends at most the boundary millisecond, and the client dedupes by
        # id, so the cost is a duplicate and the alternative is a lost event.
        sql += " AND updated_at >= ?"
        params.append(since)
    else:
        sql += " AND deleted_at IS NULL"
    sql += " " + order
    return [row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def get_row(
    conn: sqlite3.Connection, table: str, row_id: str
) -> sqlite3.Row | None:
    cols = EVENT_COLS if table == "events" else NOTE_COLS
    return conn.execute(
        f"SELECT {cols} FROM {table} WHERE id = ?", (row_id,)
    ).fetchone()


def read_settings(conn: sqlite3.Connection, scope: str) -> dict:
    """Settings are shared campaign state, stored as JSON-encoded scalars."""
    import json
    out: dict = {}
    for r in conn.execute(
        "SELECT key, value FROM campaign_settings WHERE scope = ?", (scope,)
    ):
        try:
            out[r["key"]] = json.loads(r["value"])
        except (ValueError, TypeError):
            out[r["key"]] = r["value"]
    return out


def characters_of(conn: sqlite3.Connection, player_id: str) -> list[dict]:
    return [
        row_to_dict(r)
        for r in conn.execute(
            "SELECT id, player_id, name, kind, color, active FROM characters"
            "  WHERE player_id = ? AND active = 1 ORDER BY name",
            (player_id,),
        )
    ]


def all_players(conn: sqlite3.Connection) -> list[dict]:
    """Every player, for the roster. Explicit columns: token_hash must never
    ride along, and role is not the roster's business."""
    return [
        row_to_dict(r)
        for r in conn.execute(
            "SELECT id, display_name, active FROM players ORDER BY display_name, id"
        )
    ]


def all_characters(conn: sqlite3.Connection) -> list[dict]:
    return [
        row_to_dict(r)
        for r in conn.execute(
            "SELECT id, player_id, name, kind, color, active FROM characters"
            "  ORDER BY name, id"
        )
    ]

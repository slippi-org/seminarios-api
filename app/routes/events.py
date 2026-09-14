import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import access, store
from ..db import utcnow
from ..deps import current_player, get_conn, guard_write
from ..models import EventCreate, EventPatch

router = APIRouter()
TABLE = "events"


@router.post("/events")
def create_event(
    body: EventCreate,
    response: Response,
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    guard_write(player)
    role = player["role"]

    if not access.may_set_visibility(role, body.visibility):
        raise HTTPException(403, "only a gm may create gm-visibility entries")

    # Idempotent replay: the outbox retries a POST it is not sure landed.
    existing = store.get_row(conn, TABLE, body.id)
    if existing is not None:
        vis_sql, _ = access.visible_to(role)
        visible = conn.execute(
            f"SELECT 1 FROM {TABLE} WHERE id = ? AND ({vis_sql})", (body.id,)
        ).fetchone()
        if not visible:
            raise HTTPException(409, "id already exists")
        response.status_code = 200
        return store.row_to_dict(existing)

    try:
        character_id = access.resolve_character(
            conn, role, player["id"], body.character_id
        )
    except LookupError:
        raise HTTPException(400, "unknown character")
    except PermissionError:
        raise HTTPException(403, "that character belongs to another player")

    now = utcnow(conn)
    try:
        conn.execute(
            f"INSERT INTO {TABLE} (id, scope, place_id, place, day, time_of_day, text,"
            "  author_id, character_id, visibility, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                body.id, body.scope, body.place_id, body.place, body.day,
                body.time_of_day, body.text,
                player["id"],      # author is the token's owner, never the body
                character_id, body.visibility, now, now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Two replays of the same POST raced past the check above. The row exists
        # either way, which is all the caller wanted; this is the point of
        # client-generated ids.
        conn.rollback()
        response.status_code = 200
        return store.row_to_dict(store.get_row(conn, TABLE, body.id))
    response.status_code = 201
    return store.row_to_dict(store.get_row(conn, TABLE, body.id))


@router.patch("/events/{event_id}")
def patch_event(
    event_id: str,
    body: EventPatch,
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    guard_write(player)
    role = player["role"]
    row = _load_mutable(conn, event_id, player)

    fields = body.model_dump(exclude_unset=True)
    if "visibility" in fields and not access.may_set_visibility(role, fields["visibility"]):
        raise HTTPException(403, "only a gm may set gm visibility")
    if "character_id" in fields:
        try:
            fields["character_id"] = access.resolve_character(
                conn, role, player["id"], fields["character_id"]
            )
        except LookupError:
            raise HTTPException(400, "unknown character")
        except PermissionError:
            raise HTTPException(403, "that character belongs to another player")
    if not fields:
        return store.row_to_dict(row)

    fields["updated_at"] = utcnow(conn)
    assignments = ", ".join(f"{k} = ?" for k in fields)   # keys are model fields, never input
    conn.execute(
        f"UPDATE {TABLE} SET {assignments} WHERE id = ?", (*fields.values(), event_id)
    )
    conn.commit()
    return store.row_to_dict(store.get_row(conn, TABLE, event_id))


@router.delete("/events/{event_id}")
def delete_event(
    event_id: str,
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Soft delete. Nothing in a memorial is ever hard-deleted (PLAN.md §3)."""
    guard_write(player)
    _load_mutable(conn, event_id, player)
    now = utcnow(conn)
    conn.execute(
        f"UPDATE {TABLE} SET deleted_at = ?, updated_at = ? WHERE id = ?",
        (now, now, event_id),
    )
    conn.commit()
    return store.row_to_dict(store.get_row(conn, TABLE, event_id))


def _load_mutable(
    conn: sqlite3.Connection, row_id: str, player: sqlite3.Row
) -> sqlite3.Row:
    """Fetch a row the caller may both see and change.

    An invisible row reports 404, not 403: a player must not be able to probe for
    the existence of the GM's secrets.
    """
    row = store.get_row(conn, TABLE, row_id)
    if row is None or row["deleted_at"] is not None:
        raise HTTPException(404, "not found")
    vis_sql, _ = access.visible_to(player["role"])
    visible = conn.execute(
        f"SELECT 1 FROM {TABLE} WHERE id = ? AND ({vis_sql})", (row_id,)
    ).fetchone()
    if not visible:
        raise HTTPException(404, "not found")
    if not access.may_mutate_row(player["role"], player["id"], row):
        raise HTTPException(403, "not your entry")
    return row

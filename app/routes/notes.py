"""Notes. Same shape and same rules as events (PLAN.md §6).

The old model was one shared text blob per district; these are rows, so the GM
can keep a gm-visibility note on a district alongside the party's shared one.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import access, store
from ..db import utcnow
from ..deps import current_player, get_conn, guard_write
from ..models import NoteCreate, NotePatch

router = APIRouter()
TABLE = "notes"


@router.post("/notes")
def create_note(
    body: NoteCreate,
    response: Response,
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    guard_write(player)
    role = player["role"]
    if not access.may_set_visibility(role, body.visibility):
        raise HTTPException(403, "only a gm may create gm-visibility entries")

    existing = store.get_row(conn, TABLE, body.id)
    if existing is not None:
        vis_sql, _ = access.visible_to(role)
        if not conn.execute(
            f"SELECT 1 FROM {TABLE} WHERE id = ? AND ({vis_sql})", (body.id,)
        ).fetchone():
            raise HTTPException(409, "id already exists")
        response.status_code = 200
        return store.row_to_dict(existing)

    now = utcnow(conn)
    try:
        conn.execute(
            f"INSERT INTO {TABLE} (id, scope, place_id, text, author_id, visibility,"
            "  created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (body.id, body.scope, body.place_id, body.text,
             player["id"], body.visibility, now, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        response.status_code = 200
        return store.row_to_dict(store.get_row(conn, TABLE, body.id))
    response.status_code = 201
    return store.row_to_dict(store.get_row(conn, TABLE, body.id))


@router.patch("/notes/{note_id}")
def patch_note(
    note_id: str,
    body: NotePatch,
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    guard_write(player)
    row = _load_mutable(conn, note_id, player)
    fields = body.model_dump(exclude_unset=True)
    if "visibility" in fields and not access.may_set_visibility(
        player["role"], fields["visibility"]
    ):
        raise HTTPException(403, "only a gm may set gm visibility")
    if not fields:
        return store.row_to_dict(row)

    fields["updated_at"] = utcnow(conn)
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE {TABLE} SET {assignments} WHERE id = ?", (*fields.values(), note_id)
    )
    conn.commit()
    return store.row_to_dict(store.get_row(conn, TABLE, note_id))


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: str,
    player: sqlite3.Row = Depends(current_player),
    conn: sqlite3.Connection = Depends(get_conn),
):
    guard_write(player)
    _load_mutable(conn, note_id, player)
    now = utcnow(conn)
    conn.execute(
        f"UPDATE {TABLE} SET deleted_at = ?, updated_at = ? WHERE id = ?",
        (now, now, note_id),
    )
    conn.commit()
    return store.row_to_dict(store.get_row(conn, TABLE, note_id))


def _load_mutable(
    conn: sqlite3.Connection, row_id: str, player: sqlite3.Row
) -> sqlite3.Row:
    row = store.get_row(conn, TABLE, row_id)
    if row is None or row["deleted_at"] is not None:
        raise HTTPException(404, "not found")
    vis_sql, _ = access.visible_to(player["role"])
    if not conn.execute(
        f"SELECT 1 FROM {TABLE} WHERE id = ? AND ({vis_sql})", (row_id,)
    ).fetchone():
        raise HTTPException(404, "not found")
    if not access.may_mutate_row(player["role"], player["id"], row):
        raise HTTPException(403, "not your entry")
    return row

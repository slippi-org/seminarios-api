"""The single source of truth for who may see and do what.

Deliberately one module used by every read and write path. Visibility filtering
repeated per-route is exactly how a `gm` row eventually leaks into a player's
sync, so there is one predicate here and no other.
"""
import sqlite3

from . import config

GM_ROLES = ("gm", "admin")


def visible_to(role: str | None) -> tuple[str, list]:
    """SQL fragment + params restricting rows to what `role` may read.

    role None means unauthenticated: nothing in v1, and `visibility='public'`
    only once SEM_PUBLIC_READ is flipped on.
    """
    if role in GM_ROLES:
        return "1=1", []
    if role == "player":
        return "visibility IN ('party','public')", []
    if role is None and config.PUBLIC_READ:
        return "visibility = 'public'", []
    return "0=1", []


def may_set_visibility(role: str, visibility: str) -> bool:
    """Players may publish to the party or the world, but may not forge GM secrets."""
    if visibility == "gm":
        return role in GM_ROLES
    return visibility in ("party", "public")


def may_mutate_row(role: str, player_id: str, row: sqlite3.Row) -> bool:
    """Author, or gm/admin (PLAN.md §6)."""
    return role in GM_ROLES or row["author_id"] == player_id


def may_write_settings(role: str) -> bool:
    return role in GM_ROLES


def resolve_character(
    conn: sqlite3.Connection, role: str, player_id: str, character_id: str | None
) -> str | None:
    """Validate that the caller may attribute an entry to this character.

    A player may only speak as their own characters. The GM owns every NPC, so
    gm/admin may attribute to any character that exists.
    """
    if character_id is None:
        return None
    row = conn.execute(
        "SELECT id, player_id FROM characters WHERE id = ? AND active = 1",
        (character_id,),
    ).fetchone()
    if row is None:
        raise LookupError("unknown character")
    if role not in GM_ROLES and row["player_id"] != player_id:
        raise PermissionError("character belongs to another player")
    return row["id"]

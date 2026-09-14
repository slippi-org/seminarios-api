"""SQLite access. stdlib sqlite3, no ORM (PLAN.md §10, Phase 1).

One connection per request, opened by the `conn` dependency in main.py. WAL is a
persistent property of the database file and is set once at init; foreign_keys is
per-connection and must be set every time.
"""
import sqlite3
from pathlib import Path

from . import config

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False because FastAPI runs sync endpoints in a
    # threadpool: the `get_conn` dependency and the handler it feeds may execute
    # on different worker threads. This is safe here and ONLY here because the
    # connection is per-request and handed between those threads sequentially --
    # it is never used by two requests, or two threads, at the same moment.
    conn = sqlite3.connect(path, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Two players logging during the same fight must not collide on a locked db.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init(db_path: str | None = None) -> None:
    """Apply the schema. Idempotent -- runs on every startup."""
    conn = connect(db_path)
    try:
        # WAL is what makes `sqlite3 .backup` a consistent ONLINE snapshot, which
        # is the whole reason we chose SQLite over a JSON file (PLAN.md §3).
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA.read_text())
        conn.commit()
    finally:
        conn.close()


def utcnow(conn: sqlite3.Connection) -> str:
    """Server time, from the same clock and in the same format as every DEFAULT
    in the schema. Clients never set timestamps.

    Milliseconds, not seconds. `datetime('now')` resolves to one second, which is
    coarser than play: two players logging during the same fight land in the same
    tick, and a delta sync keyed on `updated_at` then cannot separate them.
    """
    return conn.execute(
        "SELECT strftime('%Y-%m-%d %H:%M:%f','now')"
    ).fetchone()[0]

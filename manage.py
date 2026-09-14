#!/usr/bin/env python3
"""Player and character management.

Deliberately a CLI and not an HTTP surface (PLAN.md §6): the API has no admin
endpoints to find, guess, or leave unauthenticated. Run it on the Pi:

    docker exec -it seminarios-api python manage.py list-players
"""
import argparse
import secrets
import sys

from app import auth, config, db


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _print_enrollment(display_name: str, token: str) -> None:
    pretty = auth.format_token(token)
    link = f"{config.SITE_BASE_URL}/#t={pretty}"
    print(f"\n  player : {display_name}")
    print(f"  token  : {pretty}")
    print(f"  link   : {link}")
    print(
        "\n  Shown ONCE -- only the hash is stored. Send the link over WhatsApp;\n"
        "  the '#' fragment is never transmitted to a server, so the token lands\n"
        "  in neither GitHub Pages' nor Cloudflare's logs. Lost it? rotate-token.\n"
    )


def add_player(args) -> int:
    conn = db.connect()
    try:
        token = auth.new_token()
        player_id = _new_id("plr")
        conn.execute(
            "INSERT INTO players (id, display_name, role, token_hash)"
            " VALUES (?,?,?,?)",
            (player_id, args.name, args.role, auth.hash_token(token)),
        )
        conn.commit()
        print(f"created {player_id}  role={args.role}")
        _print_enrollment(args.name, token)
        return 0
    finally:
        conn.close()


def add_character(args) -> int:
    conn = db.connect()
    try:
        if conn.execute(
            "SELECT 1 FROM players WHERE id = ?", (args.player_id,)
        ).fetchone() is None:
            print(f"no such player: {args.player_id}", file=sys.stderr)
            return 1
        char_id = _new_id("chr")
        conn.execute(
            "INSERT INTO characters (id, player_id, name, kind, color)"
            " VALUES (?,?,?,?,?)",
            (char_id, args.player_id, args.name, args.kind, args.color),
        )
        conn.commit()
        print(f"created {char_id}  {args.name} ({args.kind}) -> {args.player_id}")
        return 0
    finally:
        conn.close()


def list_players(args) -> int:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT p.id, p.display_name, p.role, p.active, p.created_at,"
            "  (SELECT COUNT(*) FROM characters c"
            "     WHERE c.player_id = p.id AND c.active = 1) AS chars"
            " FROM players p ORDER BY p.created_at"
        ).fetchall()
        if not rows:
            print("no players yet -- start with:  manage.py add-player \"Name\"")
            return 0
        print(f"{'id':20} {'name':18} {'role':7} {'on':3} {'chars':5} created")
        for r in rows:
            print(
                f"{r['id']:20} {r['display_name']:18} {r['role']:7} "
                f"{'yes' if r['active'] else 'no':3} {r['chars']:<5} {r['created_at']}"
            )
        return 0
    finally:
        conn.close()


def list_characters(args) -> int:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT c.id, c.name, c.kind, c.color, c.active, p.display_name AS owner"
            " FROM characters c JOIN players p ON p.id = c.player_id"
            " ORDER BY p.display_name, c.name"
        ).fetchall()
        if not rows:
            print("no characters yet")
            return 0
        print(f"{'id':20} {'name':18} {'kind':5} {'owner':18} {'color':9} on")
        for r in rows:
            print(
                f"{r['id']:20} {r['name']:18} {r['kind']:5} {r['owner']:18} "
                f"{r['color'] or '-':9} {'yes' if r['active'] else 'no'}"
            )
        return 0
    finally:
        conn.close()


def rotate_token(args) -> int:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT display_name FROM players WHERE id = ?", (args.player_id,)
        ).fetchone()
        if row is None:
            print(f"no such player: {args.player_id}", file=sys.stderr)
            return 1
        token = auth.new_token()
        conn.execute(
            "UPDATE players SET token_hash = ? WHERE id = ?",
            (auth.hash_token(token), args.player_id),
        )
        conn.commit()
        print(f"rotated {args.player_id} -- the previous token is now dead")
        _print_enrollment(row["display_name"], token)
        return 0
    finally:
        conn.close()


def deactivate(args) -> int:
    conn = db.connect()
    try:
        cur = conn.execute(
            "UPDATE players SET active = 0 WHERE id = ?", (args.player_id,)
        )
        conn.commit()
        if cur.rowcount == 0:
            print(f"no such player: {args.player_id}", file=sys.stderr)
            return 1
        print(f"deactivated {args.player_id} -- their entries are kept")
        return 0
    finally:
        conn.close()


def stats(args) -> int:
    conn = db.connect()
    try:
        for table in ("events", "notes"):
            live = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE deleted_at IS NULL"
            ).fetchone()[0]
            gone = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE deleted_at IS NOT NULL"
            ).fetchone()[0]
            print(f"{table:8} {live} live, {gone} deleted")
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if total > config.ROW_COUNT_ALERT:
            print(f"\nWARNING: {total} event rows exceeds {config.ROW_COUNT_ALERT}."
                  " That is a bug signal, not a capacity signal.")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add-player", help="create a player and print their token once")
    p.add_argument("name")
    p.add_argument("--role", default="player", choices=["player", "gm", "admin"])
    p.set_defaults(func=add_player)

    p = sub.add_parser("add-character", help="attach a character to a player")
    p.add_argument("player_id")
    p.add_argument("name")
    p.add_argument("--kind", default="pc", choices=["pc", "npc"])
    p.add_argument("--color", default=None, help="hex, e.g. '#c9b882'")
    p.set_defaults(func=add_character)

    sub.add_parser("list-players").set_defaults(func=list_players)
    sub.add_parser("list-characters").set_defaults(func=list_characters)
    sub.add_parser("stats").set_defaults(func=stats)

    p = sub.add_parser("rotate-token", help="issue a new token, killing the old one")
    p.add_argument("player_id")
    p.set_defaults(func=rotate_token)

    p = sub.add_parser("deactivate", help="disable a player without deleting anything")
    p.add_argument("player_id")
    p.set_defaults(func=deactivate)

    args = parser.parse_args()
    db.init()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

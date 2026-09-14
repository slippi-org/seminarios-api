"""Tokens and the authenticated-caller dependency (PLAN.md §6).

Tokens are 16 characters of Crockford base32 -- ~80 bits, typeable, readable
aloud, unambiguous. They are shown once at creation and stored only as a hash, so
that a database snapshot committed to seminarios-data is not a set of live
credentials.
"""
import hashlib
import hmac
import secrets
import sqlite3

# Crockford base32: no I, L, O or U. I/L read as 1, O reads as 0, U is dropped
# so that no accidental obscenity appears in a token read aloud at the table.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
TOKEN_LEN = 16


def new_token() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(TOKEN_LEN))


def format_token(token: str) -> str:
    """Display form: K7RM-9XQ2-4TBV-8HNC."""
    t = normalize(token)
    return "-".join(t[i:i + 4] for i in range(0, len(t), 4))


def normalize(raw: str) -> str:
    """Strip dashes/whitespace, uppercase, fold the ambiguous glyphs.

    A player reading a token aloud over WhatsApp will say "oh" for 0 and "ell"
    for 1; this makes both spellings hash identically.
    """
    out = []
    for ch in raw.strip().upper():
        if ch in "-_ \t\r\n":
            continue
        if ch in "IL":
            ch = "1"
        elif ch == "O":
            ch = "0"
        out.append(ch)
    return "".join(out)


def hash_token(raw: str) -> str:
    return hashlib.sha256(normalize(raw).encode("utf-8")).hexdigest()


def lookup(conn: sqlite3.Connection, raw: str) -> sqlite3.Row | None:
    """Return the active player owning this token, or None.

    The lookup is by indexed hash column; the extra constant-time compare on the
    result guards the (already unlikely) case of a partial-match index probe.
    """
    if not raw:
        return None
    digest = hash_token(raw)
    row = conn.execute(
        "SELECT id, display_name, role, token_hash, active, created_at"
        "  FROM players WHERE token_hash = ? AND active = 1",
        (digest,),
    ).fetchone()
    if row is None:
        return None
    if not hmac.compare_digest(row["token_hash"], digest):
        return None
    return row


def bearer_from_header(header: str | None) -> str:
    """Extract the credential from an Authorization header, or '' if absent."""
    if not header:
        return ""
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()

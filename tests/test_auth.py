"""Token handling. PLAN.md §6."""
import pytest

from app import auth
from tests.conftest import API, hdr


def test_token_is_crockford_base32_and_80_bits():
    t = auth.new_token()
    assert len(t) == 16
    assert set(t) <= set(auth.ALPHABET)
    # The ambiguous glyphs must not be generated at all.
    assert not (set(t) & set("ILOU"))


@pytest.mark.parametrize("spelling", [
    "k7rm9xq24tbv8hnc",          # lowercase
    "K7RM-9XQ2-4TBV-8HNC",       # grouped
    "  K7RM 9XQ2 4TBV 8HNC  ",   # spoken aloud, transcribed with spaces
    "K7RM-9XQ2-4TBV-8HNC\n",     # pasted with a trailing newline
])
def test_normalization_folds_every_plausible_spelling(spelling):
    assert auth.hash_token(spelling) == auth.hash_token("K7RM9XQ24TBV8HNC")


def test_ambiguous_glyphs_fold_to_digits():
    # A player reading aloud says "oh" for 0 and "ell"/"eye" for 1.
    assert auth.normalize("ILOilo") == "110110"
    assert auth.hash_token("0123") == auth.hash_token("OIZ3".replace("Z", "2"))


def test_token_is_never_stored_in_the_clear(client, make_player):
    from app import db
    pid, token = make_player()
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM players WHERE id = ?", (pid,)).fetchone()
    finally:
        conn.close()
    stored = " ".join(str(v) for v in tuple(row))
    assert auth.normalize(token) not in stored.upper()
    assert row["token_hash"] == auth.hash_token(token)


def test_healthz_needs_no_token(client):
    assert client.get("/healthz").status_code == 200


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer wrong-token-entirely"},
    {"Authorization": "Basic K7RM9XQ24TBV8HNC"},
    {"Authorization": "K7RM9XQ24TBV8HNC"},
])
def test_protected_routes_reject_bad_credentials(client, headers):
    assert client.get(f"{API}/me", headers=headers).status_code == 401


def test_deactivated_player_cannot_authenticate(client, make_player):
    from app import db
    pid, token = make_player()
    assert client.get(f"{API}/me", headers=hdr(token)).status_code == 200
    conn = db.connect()
    conn.execute("UPDATE players SET active = 0 WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    assert client.get(f"{API}/me", headers=hdr(token)).status_code == 401


def test_me_reports_role_and_characters(client, make_player, make_character):
    pid, token = make_player("Aaron", role="admin")
    make_character(pid, "Gondgieaux", color="#c9b882")
    body = client.get(f"{API}/me", headers=hdr(token)).json()
    assert body["role"] == "admin"
    assert body["player"]["display_name"] == "Aaron"
    assert [c["name"] for c in body["characters"]] == ["Gondgieaux"]
    assert body["characters"][0]["color"] == "#c9b882"
    assert body["server_time"]

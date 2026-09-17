"""GET /roster: names and colours for everyone, so the frontend can attribute
another player's event and the GM can pick any NPC (PLAN.md §6, known gap)."""
from tests.conftest import API, hdr


def test_roster_requires_a_token(client):
    assert client.get(f"{API}/roster").status_code == 401


def test_player_sees_every_player_and_character(client, make_player, make_character):
    gm_id, gm_token = make_player("GM", role="gm")
    bill_id, bill_token = make_player("Bill", role="player")
    ann_id, _ = make_player("Ann", role="player")
    gond = make_character(bill_id, "Gondgieaux", color="#c9b882")
    vex = make_character(gm_id, "Vex the potion merchant", kind="npc")
    xgh = make_character(ann_id, "Xghchli", color="#88aaff")

    r = client.get(f"{API}/roster", headers=hdr(bill_token))
    assert r.status_code == 200
    body = r.json()

    assert {p["id"] for p in body["players"]} == {gm_id, bill_id, ann_id}
    assert {c["id"] for c in body["characters"]} == {gond, vex, xgh}

    by_id = {c["id"]: c for c in body["characters"]}
    assert by_id[vex]["player_id"] == gm_id
    assert by_id[vex]["kind"] == "npc"
    assert by_id[gond]["color"] == "#c9b882"
    assert by_id[gond]["name"] == "Gondgieaux"


def test_roster_never_carries_secrets(client, make_player):
    _, token = make_player("Bill")
    make_player("GM", role="gm")
    body = client.get(f"{API}/roster", headers=hdr(token)).json()
    for p in body["players"]:
        assert set(p) == {"id", "display_name", "active"}
    assert "token_hash" not in client.get(f"{API}/roster", headers=hdr(token)).text


def test_roster_is_the_same_for_every_role(client, make_player, make_character):
    gm_id, gm_token = make_player("GM", role="gm")
    bill_id, bill_token = make_player("Bill")
    make_character(gm_id, "Secret NPC", kind="npc")
    make_character(bill_id, "Gondgieaux")
    as_gm = client.get(f"{API}/roster", headers=hdr(gm_token)).json()
    as_player = client.get(f"{API}/roster", headers=hdr(bill_token)).json()
    assert as_gm == as_player


def test_inactive_rows_are_included_and_flagged(client, make_player, make_character):
    """A departed player still authored their entries; the memorial keeps the name."""
    from app import db

    bill_id, bill_token = make_player("Bill")
    gone_id, _ = make_player("Gone")
    retired = make_character(gone_id, "Retired PC")
    conn = db.connect()
    conn.execute("UPDATE players SET active = 0 WHERE id = ?", (gone_id,))
    conn.execute("UPDATE characters SET active = 0 WHERE id = ?", (retired,))
    conn.commit()
    conn.close()

    body = client.get(f"{API}/roster", headers=hdr(bill_token)).json()
    players = {p["id"]: p for p in body["players"]}
    chars = {c["id"]: c for c in body["characters"]}
    assert players[gone_id]["active"] == 0
    assert players[bill_id]["active"] == 1
    assert chars[retired]["active"] == 0


def test_roster_order_is_stable(client, make_player, make_character):
    bill_id, token = make_player("Bill")
    make_player("Ann")
    make_character(bill_id, "Zed")
    make_character(bill_id, "Abe")
    body = client.get(f"{API}/roster", headers=hdr(token)).json()
    assert [p["display_name"] for p in body["players"]] == ["Ann", "Bill"]
    assert [c["name"] for c in body["characters"]] == ["Abe", "Zed"]

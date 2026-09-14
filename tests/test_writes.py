"""Write rules: authorship, character ownership, idempotency, soft delete."""
import secrets

from tests.conftest import API, hdr, make_event


def test_author_comes_from_the_token_not_the_body(client, make_player):
    """The old 'Playing as' dropdown was honour-system. This is the fix."""
    victim_id, _ = make_player("Victim", role="player")
    _, forger_token = make_player("Forger", role="player")
    r = make_event(client, forger_token, id="evt_forged", author_id=victim_id,
                   author=victim_id)
    assert r.status_code == 201
    assert r.json()["author_id"] != victim_id


def test_timestamps_are_server_assigned(client, make_player):
    _, token = make_player()
    r = make_event(client, token, id="evt_ts",
                   created_at="1999-01-01 00:00:00",
                   updated_at="1999-01-01 00:00:00")
    assert not r.json()["created_at"].startswith("1999")


def test_player_may_not_speak_as_another_players_character(
    client, make_player, make_character
):
    other_id, _ = make_player("Other", role="player")
    theirs = make_character(other_id, "Xghchli")
    _, token = make_player("Bill", role="player")
    r = make_event(client, token, character_id=theirs)
    assert r.status_code == 403


def test_gm_owns_every_npc(client, make_player, make_character):
    player_id, _ = make_player("Bill", role="player")
    npc = make_character(player_id, "Vex the potion merchant", kind="npc")
    _, gm_token = make_player("GM", role="gm")
    r = make_event(client, gm_token, character_id=npc)
    assert r.status_code == 201
    assert r.json()["character_id"] == npc


def test_own_character_is_accepted(client, make_player, make_character):
    pid, token = make_player("Bill", role="player")
    mine = make_character(pid, "Gondgieaux")
    r = make_event(client, token, character_id=mine)
    assert r.status_code == 201 and r.json()["character_id"] == mine


def test_unknown_character_is_rejected(client, make_player):
    _, token = make_player()
    assert make_event(client, token, character_id="chr_doesnotexist").status_code == 400


def test_replayed_post_is_idempotent(client, make_player):
    """The outbox retries a POST it is not sure landed."""
    _, token = make_player()
    first = make_event(client, token, id="evt_same", text="original")
    assert first.status_code == 201
    again = make_event(client, token, id="evt_same", text="a different body")
    assert again.status_code == 200
    assert again.json()["text"] == "original"
    state = client.get(f"{API}/state", headers=hdr(token)).json()
    assert sum(1 for e in state["events"] if e["id"] == "evt_same") == 1


def test_delete_is_soft_and_surfaces_as_a_tombstone(client, make_player):
    _, token = make_player()
    make_event(client, token, id="evt_gone")
    before = client.get(f"{API}/state", headers=hdr(token)).json()["server_time"]
    assert client.delete(f"{API}/events/evt_gone", headers=hdr(token)).status_code == 200

    # A full load skips graves...
    full = client.get(f"{API}/state", headers=hdr(token)).json()
    assert "evt_gone" not in {e["id"] for e in full["events"]}
    # ...but a delta must carry them, or a client never learns of the deletion.
    delta = client.get(f"{API}/state", params={"since": before},
                       headers=hdr(token)).json()
    tomb = [e for e in delta["events"] if e["id"] == "evt_gone"]
    assert tomb and tomb[0]["deleted_at"]


def test_player_cannot_edit_or_delete_another_players_entry(client, make_player):
    _, mine = make_player("A", role="player")
    _, theirs = make_player("B", role="player")
    make_event(client, mine, id="evt_a", visibility="party")
    assert client.patch(f"{API}/events/evt_a", json={"text": "hacked"},
                        headers=hdr(theirs)).status_code == 403
    assert client.delete(f"{API}/events/evt_a", headers=hdr(theirs)).status_code == 403


def test_gm_may_edit_anyones_entry(client, make_player):
    _, pl = make_player("Bill", role="player")
    _, gm = make_player("GM", role="gm")
    make_event(client, pl, id="evt_x", visibility="party")
    r = client.patch(f"{API}/events/evt_x", json={"text": "corrected"}, headers=hdr(gm))
    assert r.status_code == 200 and r.json()["text"] == "corrected"


def test_elsewhere_events_have_no_district(client, make_player):
    """'Elsewhere -- no district' is a real option: travel, the open sea."""
    _, token = make_player()
    r = make_event(client, token, place_id=None, place="three days out of port")
    assert r.status_code == 201
    assert r.json()["place_id"] is None
    assert r.json()["place"] == "three days out of port"


def test_day_is_an_integer_ordinal(client, make_player):
    _, token = make_player()
    assert make_event(client, token, day=1_620_032).json()["day"] == 1_620_032
    assert make_event(client, token, day="day-3").status_code == 422


def test_text_length_and_blankness_are_enforced(client, make_player):
    from app import config
    _, token = make_player()
    assert make_event(client, token, text="x" * (config.MAX_EVENT_TEXT + 1)).status_code == 422
    assert make_event(client, token, text="   ").status_code == 422
    assert make_event(client, token, text="x" * config.MAX_EVENT_TEXT).status_code == 201


def test_oversized_body_is_refused_before_it_is_read(client, make_player):
    from app import config
    _, token = make_player()
    r = client.post(
        f"{API}/events",
        headers={**hdr(token), "Content-Type": "application/json"},
        content=b'{"pad":"' + b"x" * (config.MAX_BODY_BYTES + 16) + b'"}',
    )
    assert r.status_code == 413


def test_events_sort_by_time_of_day_not_alphabetically(client, make_player):
    """Alphabetical would give afternoon, evening, midday, morning, night."""
    _, token = make_player()
    for t in ("night", "morning", "evening", "midday", "afternoon"):
        make_event(client, token, id=f"evt_{t}", day=5, time_of_day=t)
    order = [e["time_of_day"] for e in
             client.get(f"{API}/state", headers=hdr(token)).json()["events"]]
    assert order == ["morning", "midday", "afternoon", "evening", "night"]


def test_concurrent_replays_of_one_post_do_not_500(client, make_player):
    """The outbox flushes on reconnect; two tabs can retry the same id at once.
    Whoever loses the insert race must still get the row, not a 500."""
    from concurrent.futures import ThreadPoolExecutor

    _, token = make_player()
    body = {
        "id": "evt_race", "place_id": "12_market", "day": 1_620_032,
        "time_of_day": "evening", "text": "same event, twice", "visibility": "party",
    }
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [f.result() for f in
                   [pool.submit(client.post, f"{API}/events", json=body,
                                headers=hdr(token)) for _ in range(8)]]

    codes = sorted(r.status_code for r in results)
    assert all(c in (200, 201) for c in codes), codes
    assert codes.count(201) == 1, f"more than one insert won: {codes}"
    assert all(r.json()["id"] == "evt_race" for r in results)

    state = client.get(f"{API}/state", headers=hdr(token)).json()
    assert sum(1 for e in state["events"] if e["id"] == "evt_race") == 1


def test_unknown_body_keys_cannot_reach_the_update_statement(client, make_player):
    """PATCH builds `SET a = ?, b = ?` from model_dump() keys. If pydantic ever
    let an undeclared key through, that string would be attacker-controlled SQL."""
    from app.models import EventPatch

    hostile = EventPatch.model_validate({
        "text": "legitimate",
        "visibility": "party",
        "author_id": "plr_someone_else",
        "deleted_at": "2020-01-01",
        "text = 'pwned' WHERE 1=1 --": "x",
    })
    assert set(hostile.model_dump(exclude_unset=True)) == {"text", "visibility"}


def test_patch_cannot_reassign_authorship_or_resurrect_a_row(client, make_player):
    _, mine = make_player("A", role="player")
    victim_id, _ = make_player("B", role="player")
    make_event(client, mine, id="evt_own", text="mine")
    before = client.get(f"{API}/state", headers=hdr(mine)).json()["events"][0]

    r = client.patch(f"{API}/events/evt_own", headers=hdr(mine), json={
        "text": "edited", "author_id": victim_id, "deleted_at": None,
        "created_at": "1999-01-01 00:00:00",
    })
    assert r.status_code == 200
    after = r.json()
    assert after["text"] == "edited"
    assert after["author_id"] == before["author_id"] != victim_id
    assert after["created_at"] == before["created_at"]

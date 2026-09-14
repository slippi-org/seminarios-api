"""Visibility filtering. The failure this file exists to prevent is a
gm-visibility row reaching a player -- PLAN.md §6, read filtering."""
from tests.conftest import API, hdr, make_event


def test_player_cannot_see_gm_rows_in_state(client, make_player):
    _, gm_token = make_player("GM", role="gm")
    _, pl_token = make_player("Bill", role="player")

    make_event(client, gm_token, id="evt_secret", visibility="gm",
               text="the duke is a doppelganger")
    make_event(client, gm_token, id="evt_open", visibility="party",
               text="it rained")

    seen = client.get(f"{API}/state", headers=hdr(pl_token)).json()
    ids = {e["id"] for e in seen["events"]}
    assert ids == {"evt_open"}
    assert "doppelganger" not in client.get(f"{API}/state", headers=hdr(pl_token)).text


def test_gm_sees_everything(client, make_player):
    _, gm_token = make_player("GM", role="gm")
    _, pl_token = make_player("Bill", role="player")
    make_event(client, gm_token, id="evt_secret", visibility="gm")
    make_event(client, pl_token, id="evt_party", visibility="party")
    ids = {e["id"] for e in client.get(f"{API}/state", headers=hdr(gm_token)).json()["events"]}
    assert ids == {"evt_secret", "evt_party"}


def test_admin_sees_everything_too(client, make_player):
    _, gm_token = make_player("GM", role="gm")
    _, admin_token = make_player("Aaron", role="admin")
    make_event(client, gm_token, id="evt_secret", visibility="gm")
    ids = {e["id"] for e in client.get(f"{API}/state", headers=hdr(admin_token)).json()["events"]}
    assert "evt_secret" in ids


def test_player_cannot_create_a_gm_row(client, make_player):
    _, pl_token = make_player("Bill", role="player")
    r = make_event(client, pl_token, visibility="gm")
    assert r.status_code == 403


def test_player_cannot_escalate_their_own_row_to_gm(client, make_player):
    _, pl_token = make_player("Bill", role="player")
    make_event(client, pl_token, id="evt_mine", visibility="party")
    r = client.patch(f"{API}/events/evt_mine", json={"visibility": "gm"},
                     headers=hdr(pl_token))
    assert r.status_code == 403


def test_gm_row_is_404_not_403_for_a_player(client, make_player):
    """A player must not be able to probe for the existence of GM secrets."""
    _, gm_token = make_player("GM", role="gm")
    _, pl_token = make_player("Bill", role="player")
    make_event(client, gm_token, id="evt_secret", visibility="gm")
    for method in ("patch", "delete"):
        call = getattr(client, method)
        kwargs = {"json": {"text": "x"}} if method == "patch" else {}
        r = call(f"{API}/events/evt_secret", headers=hdr(pl_token), **kwargs)
        assert r.status_code == 404, method


def test_gm_notes_are_filtered_the_same_way(client, make_player):
    _, gm_token = make_player("GM", role="gm")
    _, pl_token = make_player("Bill", role="player")
    client.post(f"{API}/notes", headers=hdr(gm_token), json={
        "id": "note_secret", "place_id": "23_red-light",
        "text": "Vex reports to the Duke", "visibility": "gm"})
    client.post(f"{API}/notes", headers=hdr(pl_token), json={
        "id": "note_party", "place_id": "23_red-light",
        "text": "do not trust Vex", "visibility": "party"})
    body = client.get(f"{API}/state", headers=hdr(pl_token))
    assert {n["id"] for n in body.json()["notes"]} == {"note_party"}
    assert "Duke" not in body.text


def test_unauthenticated_reads_nothing_while_public_read_is_off(client, make_player):
    _, gm_token = make_player("GM", role="gm")
    make_event(client, gm_token, id="evt_public", visibility="public")
    assert client.get(f"{API}/state").status_code == 401


def test_public_read_flag_exposes_only_public_rows(client, make_player, monkeypatch):
    from app import config
    _, gm_token = make_player("GM", role="gm")
    make_event(client, gm_token, id="evt_public", visibility="public")
    make_event(client, gm_token, id="evt_party", visibility="party")
    make_event(client, gm_token, id="evt_secret", visibility="gm")

    # The flag governs the predicate; the route still requires a token in v1.
    from app.access import visible_to
    monkeypatch.setattr(config, "PUBLIC_READ", True)
    assert visible_to(None) == ("visibility = 'public'", [])
    monkeypatch.setattr(config, "PUBLIC_READ", False)
    assert visible_to(None) == ("0=1", [])

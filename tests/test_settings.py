"""Shared campaign settings -- so the party agrees about what day it is."""
from tests.conftest import API, hdr


def test_player_cannot_change_settings(client, make_player):
    _, token = make_player("Bill", role="player")
    assert client.put(f"{API}/settings", json={"today": 6329},
                      headers=hdr(token)).status_code == 403


def test_gm_sets_today_and_everyone_sees_it(client, make_player):
    _, gm = make_player("GM", role="gm")
    _, pl = make_player("Bill", role="player")
    r = client.put(f"{API}/settings",
                   json={"today": 1_620_040, "era": "common",
                         "campaignStart": 1_620_032}, headers=hdr(gm))
    assert r.status_code == 200
    seen = client.get(f"{API}/state", headers=hdr(pl)).json()["settings"]
    assert seen == {"today": 1_620_040, "era": "common",
                    "campaignStart": 1_620_032}


def test_put_is_partial(client, make_player):
    _, gm = make_player("GM", role="gm")
    client.put(f"{API}/settings", json={"era": "aeronian", "today": 1},
               headers=hdr(gm))
    client.put(f"{API}/settings", json={"today": 2}, headers=hdr(gm))
    settings = client.get(f"{API}/settings", headers=hdr(gm)).json()["settings"]
    assert settings == {"era": "aeronian", "today": 2}


def test_settings_preserve_integer_type(client, make_player):
    """`today` is an absolute day ordinal; it must not come back as a string."""
    _, gm = make_player("GM", role="gm")
    client.put(f"{API}/settings", json={"today": 1_620_032}, headers=hdr(gm))
    value = client.get(f"{API}/settings", headers=hdr(gm)).json()["settings"]["today"]
    assert value == 1_620_032 and isinstance(value, int)

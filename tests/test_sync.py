"""Delta sync -- the contract the frontend's polling loop depends on."""
import time

from tests.conftest import API, hdr, make_event


def test_full_load_then_delta(client, make_player):
    _, token = make_player()
    make_event(client, token, id="evt_1", text="first")
    full = client.get(f"{API}/state", headers=hdr(token)).json()
    assert {e["id"] for e in full["events"]} == {"evt_1"}

    make_event(client, token, id="evt_2", text="second")
    delta = client.get(f"{API}/state", params={"since": full["server_time"]},
                       headers=hdr(token)).json()
    assert "evt_2" in {e["id"] for e in delta["events"]}


def test_a_write_in_the_same_tick_as_the_cursor_is_not_lost(client, make_player):
    """The regression this suite exists for. `datetime('now')` resolves to one
    second; two players logging during the same fight share a tick, and an
    exclusive `>` window drops the second one forever."""
    _, token = make_player()
    for i in range(25):
        cursor = client.get(f"{API}/state", headers=hdr(token)).json()["server_time"]
        make_event(client, token, id=f"evt_race{i}", text=f"burst {i}")
        delta = client.get(f"{API}/state", params={"since": cursor},
                           headers=hdr(token)).json()
        assert f"evt_race{i}" in {e["id"] for e in delta["events"]}, (
            f"iteration {i}: write landed in the cursor's own tick and vanished")


def test_timestamps_have_sub_second_resolution(client, make_player):
    _, token = make_player()
    stamps = {make_event(client, token, id=f"evt_t{i}").json()["created_at"]
              for i in range(20)}
    assert len(stamps) > 1, "all 20 writes share one timestamp"
    assert any("." in s for s in stamps), "timestamps are not sub-second"


def test_server_time_is_read_before_rows(client, make_player):
    """So a write committed mid-request is re-sent, never skipped."""
    _, token = make_player()
    body = client.get(f"{API}/state", headers=hdr(token)).json()
    later = client.get(f"{API}/state", headers=hdr(token)).json()
    assert later["server_time"] >= body["server_time"]


def test_edits_reappear_in_a_delta(client, make_player):
    _, token = make_player()
    make_event(client, token, id="evt_edit", text="before")
    cursor = client.get(f"{API}/state", headers=hdr(token)).json()["server_time"]
    time.sleep(0.01)
    client.patch(f"{API}/events/evt_edit", json={"text": "after"}, headers=hdr(token))
    delta = client.get(f"{API}/state", params={"since": cursor},
                       headers=hdr(token)).json()
    edited = [e for e in delta["events"] if e["id"] == "evt_edit"]
    assert edited and edited[0]["text"] == "after"


def test_scope_isolates_rows(client, make_player):
    """`scope` is the seam for the wider world beyond Seminarios."""
    _, token = make_player()
    make_event(client, token, id="evt_here", scope="seminarios")
    make_event(client, token, id="evt_elsewhere", scope="aeronia")
    here = client.get(f"{API}/state", params={"scope": "seminarios"},
                      headers=hdr(token)).json()
    assert {e["id"] for e in here["events"]} == {"evt_here"}


def test_two_players_logging_at_once_lose_nothing(client, make_player):
    """PLAN.md §3's stated reason for choosing SQLite over a JSON file:
    'Two players logging during the same fight must not lose a write.'"""
    from concurrent.futures import ThreadPoolExecutor

    tokens = [make_player(f"P{i}")[1] for i in range(4)]
    sent = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = []
        for round_ in range(6):
            for i, tk in enumerate(tokens):
                eid = f"evt_p{i}r{round_}"
                sent.append(eid)
                futures.append(pool.submit(
                    make_event, client, tk, id=eid, day=1_620_032,
                    time_of_day="evening", text=f"player {i}, round {round_}"))
        codes = [f.result().status_code for f in futures]

    assert set(codes) == {201}, f"unexpected statuses: {sorted(set(codes))}"
    gm_view = client.get(f"{API}/state", headers=hdr(tokens[0])).json()
    assert {e["id"] for e in gm_view["events"]} == set(sent), "a write was lost"


def test_each_event_is_attributed_to_its_own_writer(client, make_player):
    """Concurrency must not cross authorship between simultaneous writers."""
    from concurrent.futures import ThreadPoolExecutor

    players = [make_player(f"P{i}") for i in range(4)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(
            lambda pair: make_event(client, pair[1][1], id=f"evt_{pair[0]}"),
            list(enumerate(players))))

    rows = {e["id"]: e["author_id"]
            for e in client.get(f"{API}/state",
                                headers=hdr(players[0][1])).json()["events"]}
    for i, (pid, _) in enumerate(players):
        assert rows[f"evt_{i}"] == pid, f"evt_{i} attributed to the wrong player"

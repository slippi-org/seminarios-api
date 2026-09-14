"""Rate limiting. The edge rule is the real defense; this is the backstop."""
from app import config, limits
from tests.conftest import API, hdr, make_event


def test_write_limit_is_per_token(client, make_player, monkeypatch):
    monkeypatch.setattr(config, "WRITES_PER_MIN", 3)
    _, a = make_player("A")
    _, b = make_player("B")
    for i in range(3):
        assert make_event(client, a, id=f"evt_a{i}").status_code == 201
    assert make_event(client, a, id="evt_a_over").status_code == 429
    # B is unaffected by A's exhaustion.
    assert make_event(client, b, id="evt_b0").status_code == 201


def test_reads_are_not_rate_limited(client, make_player, monkeypatch):
    monkeypatch.setattr(config, "WRITES_PER_MIN", 1)
    _, token = make_player()
    make_event(client, token)
    for _ in range(10):
        assert client.get(f"{API}/state", headers=hdr(token)).status_code == 200


def test_failed_auth_is_throttled_per_ip(client, monkeypatch):
    monkeypatch.setattr(config, "FAILED_AUTH_PER_MIN", 3)
    limits.reset()
    for _ in range(3):
        assert client.get(f"{API}/me", headers=hdr("BADTOKEN")).status_code == 401
    assert client.get(f"{API}/me", headers=hdr("BADTOKEN")).status_code == 429


def test_throttled_client_does_not_extend_its_own_penalty(monkeypatch):
    """A retry loop must not keep pushing its own window forward."""
    monkeypatch.setattr(config, "WRITES_PER_MIN", 2)
    limits.reset()
    now = 1000.0
    assert limits.check_write("p", now) is None
    assert limits.check_write("p", now) is None
    for _ in range(50):
        assert limits.check_write("p", now + 1) is not None
    # 60s after the two ALLOWED writes, the window is clear again.
    assert limits.check_write("p", now + 61) is None

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


def test_429_says_when_to_come_back(client, make_player, monkeypatch):
    """A 429 without Retry-After makes every client guess (PLAN.md §7.5)."""
    monkeypatch.setattr(config, "WRITES_PER_MIN", 2)
    limits.reset()
    _, token = make_player()
    for i in range(2):
        assert make_event(client, token, id=f"evt_r{i}").status_code == 201
    res = make_event(client, token, id="evt_r_over")
    assert res.status_code == 429
    # The window is a minute and the writes just happened, so the wait is the
    # rest of that minute -- a real number, not a fixed guess.
    assert 1 <= int(res.headers["retry-after"]) <= 60


def test_retry_after_shrinks_as_the_window_slides(monkeypatch):
    monkeypatch.setattr(config, "WRITES_PER_MIN", 1)
    limits.reset()
    now = 1000.0
    assert limits.check_write("p", now) is None
    assert limits.check_write("p", now + 1).retry_after == 59
    assert limits.check_write("p", now + 59.5).retry_after == 1
    # Never zero: a client told to wait no time at all is a client in a hot loop.
    assert limits.check_write("p", now + 59.99).retry_after == 1
    assert limits.check_write("p", now + 60.5) is None


def test_the_day_limit_says_come_back_tomorrow(monkeypatch):
    monkeypatch.setattr(config, "WRITES_PER_MIN", 10_000)
    monkeypatch.setattr(config, "WRITES_PER_DAY", 2)
    limits.reset()
    now = 1000.0
    assert limits.check_write("p", now) is None
    assert limits.check_write("p", now + 1) is None
    refusal = limits.check_write("p", now + 2)
    assert "day" in refusal.reason
    assert refusal.retry_after == 86_398


def test_a_locked_out_ip_is_told_how_long(client, monkeypatch):
    monkeypatch.setattr(config, "FAILED_AUTH_PER_MIN", 2)
    limits.reset()
    for _ in range(2):
        client.get(f"{API}/me", headers=hdr("BADTOKEN"))
    res = client.get(f"{API}/me", headers=hdr("BADTOKEN"))
    assert res.status_code == 429
    assert 1 <= int(res.headers["retry-after"]) <= 60


def test_retry_after_is_readable_cross_origin(client, make_player, monkeypatch):
    """A browser cannot see the header at all unless CORS exposes it."""
    monkeypatch.setattr(config, "WRITES_PER_MIN", 1)
    limits.reset()
    _, token = make_player()
    origin = config.CORS_ORIGINS[0]
    make_event(client, token, id="evt_x0")
    res = client.post(
        f"{API}/events",
        headers={**hdr(token), "Origin": origin},
        json={"id": "evt_x1", "day": 1, "text": "over"},
    )
    assert res.status_code == 429
    exposed = res.headers["access-control-expose-headers"].lower()
    assert "retry-after" in exposed

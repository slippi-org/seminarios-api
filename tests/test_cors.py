"""CORS. The frontend is a different origin on purpose (PLAN.md §2)."""
from app import config
from tests.conftest import API, hdr

ORIGIN = "https://seminarios.slippi.org"


def test_preflight_allows_the_real_origin_and_authorization_header(client):
    r = client.options(f"{API}/events", headers={
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert "authorization" in r.headers["access-control-allow-headers"].lower()


def test_origin_is_exact_never_wildcard(client, make_player):
    _, token = make_player()
    r = client.get(f"{API}/me", headers={**hdr(token), "Origin": ORIGIN})
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert r.headers.get("access-control-allow-origin") != "*"


def test_unknown_origin_is_not_granted_access(client):
    r = client.options(f"{API}/events", headers={
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
    })
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"


def test_configured_origins_never_contain_a_wildcard():
    assert "*" not in config.CORS_ORIGINS

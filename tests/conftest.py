import secrets

import pytest
from fastapi.testclient import TestClient

from app import auth, config, db, limits
from app.main import app

API = "/api/v1"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.sqlite"))
    monkeypatch.setattr(config, "PUBLIC_READ", False)
    limits.reset()
    db.init()
    with TestClient(app) as c:
        yield c
    limits.reset()


@pytest.fixture
def make_player():
    """Create a player directly in the DB and return (player_id, raw_token)."""
    def _make(name="Player", role="player"):
        conn = db.connect()
        try:
            token = auth.new_token()
            pid = f"plr_{secrets.token_hex(6)}"
            conn.execute(
                "INSERT INTO players (id, display_name, role, token_hash)"
                " VALUES (?,?,?,?)",
                (pid, name, role, auth.hash_token(token)),
            )
            conn.commit()
            return pid, token
        finally:
            conn.close()
    return _make


@pytest.fixture
def make_character():
    def _make(player_id, name="Somebody", kind="pc", color=None):
        conn = db.connect()
        try:
            cid = f"chr_{secrets.token_hex(6)}"
            conn.execute(
                "INSERT INTO characters (id, player_id, name, kind, color)"
                " VALUES (?,?,?,?,?)",
                (cid, player_id, name, kind, color),
            )
            conn.commit()
            return cid
        finally:
            conn.close()
    return _make


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


def make_event(client, token, **over):
    body = {
        "id": over.pop("id", f"evt_{secrets.token_hex(6)}"),
        "place_id": "12_market",
        "day": 1_620_032,
        "time_of_day": "evening",
        "text": "a thing happened",
        "visibility": "party",
    }
    body.update(over)
    return client.post(f"{API}/events", json=body, headers=hdr(token))

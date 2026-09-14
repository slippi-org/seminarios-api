-- Seminarios API schema. Mirrors PLAN.md §5.
-- Applied idempotently on every startup; safe to re-run.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS players (
  id           TEXT PRIMARY KEY,               -- 'plr_' + 12 hex
  display_name TEXT NOT NULL,
  role         TEXT NOT NULL DEFAULT 'player'
                 CHECK (role IN ('player','gm','admin')),
  token_hash   TEXT NOT NULL UNIQUE,           -- sha256 hex of the normalized token
  active       INTEGER NOT NULL DEFAULT 1,
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now'))
);

CREATE TABLE IF NOT EXISTS characters (
  id        TEXT PRIMARY KEY,                  -- 'chr_' + 12 hex
  player_id TEXT NOT NULL REFERENCES players(id),
  name      TEXT NOT NULL,
  kind      TEXT NOT NULL DEFAULT 'pc' CHECK (kind IN ('pc','npc')),
  color     TEXT,                              -- '#c9b882'; drives calendar dots + timeline marks
  active    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_characters_player ON characters(player_id);

CREATE TABLE IF NOT EXISTS events (
  id           TEXT PRIMARY KEY,               -- client-generated, e.g. 'evt_' + ULID
  scope        TEXT NOT NULL DEFAULT 'seminarios',
  place_id     TEXT,                           -- '12_market'; NULL is "Elsewhere"
  place        TEXT,                           -- optional free text, e.g. "Vex's stall"
  day          INTEGER NOT NULL,               -- absolute day ordinal; opaque to the server
  time_of_day  TEXT CHECK (time_of_day IN
                 ('morning','midday','afternoon','evening','night')),
  text         TEXT NOT NULL,
  author_id    TEXT NOT NULL REFERENCES players(id),
  character_id TEXT REFERENCES characters(id),
  visibility   TEXT NOT NULL DEFAULT 'party'
                 CHECK (visibility IN ('gm','party','public')),
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')),
  updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')),
  deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_updated ON events(updated_at);
CREATE INDEX IF NOT EXISTS idx_events_place   ON events(scope, place_id);
CREATE INDEX IF NOT EXISTS idx_events_order   ON events(scope, day, time_of_day, created_at, id);

CREATE TABLE IF NOT EXISTS notes (
  id         TEXT PRIMARY KEY,
  scope      TEXT NOT NULL DEFAULT 'seminarios',
  place_id   TEXT,
  text       TEXT NOT NULL,
  author_id  TEXT NOT NULL REFERENCES players(id),
  visibility TEXT NOT NULL DEFAULT 'party'
               CHECK (visibility IN ('gm','party','public')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')),
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at);
CREATE INDEX IF NOT EXISTS idx_notes_place   ON notes(scope, place_id);

CREATE TABLE IF NOT EXISTS campaign_settings (
  scope      TEXT NOT NULL DEFAULT 'seminarios',
  key        TEXT NOT NULL,                    -- 'era' | 'campaignStart' | 'today'
  value      TEXT NOT NULL,                    -- JSON-encoded scalar
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')),
  PRIMARY KEY (scope, key)
);

# 🌋🛠️ seminarios-api.git

The backend for the [seminarios.git](https://github.com/slippi-org/seminarios.git) lore
consolidation system — an authenticated event and note log for the Free City of
Seminarios, serving [seminarios.slippi.org](https://seminarios.slippi.org).

FastAPI + stdlib `sqlite3`, no ORM. The architecture and the reasoning behind it live in
`docs/homelab/seminarios/PLAN.md` in `leependu/gitility`; this README covers only how to
run the thing.

> **This repo is public and contains no secrets.** Configuration is environment
> variables (see `.env.example`); the real values live next to the compose file on the
> Pi. Nothing about deployment belongs here.

## 📜 Quick start

```bash
uv venv && uv pip install -e '.[dev]'
uv run pytest -q                          # 67 tests

# a local server against a throwaway database
SEM_DB_PATH=./data/dev.sqlite \
SEM_CORS_ORIGINS=http://localhost:8899 \
  uv run uvicorn app.main:app --reload --port 9286
```

Interactive docs at `http://localhost:9286/docs`.

## 🔑 Players and tokens

Player management is a CLI, not an HTTP surface — the API has no admin endpoints to
find, guess, or leave unauthenticated.

```bash
python manage.py add-player "Bill" --role player     # prints the token ONCE
python manage.py add-character plr_abc123 "Gondgieaux" --color '#c9b882'
python manage.py list-players
python manage.py list-characters
python manage.py rotate-token plr_abc123             # kills the previous token
python manage.py deactivate plr_abc123               # keeps their entries
python manage.py stats
```

On the Pi, prefix with `docker exec -it seminarios-api`.

Tokens are 16 characters of Crockford base32 (~80 bits), shown grouped as
`K7RM-9XQ2-4TBV-8HNC`. Only a SHA-256 hash is stored, so a database snapshot committed to
`seminarios-data` is not a set of live credentials. Normalization folds the spellings a
player might actually type or read aloud: case, dashes, spaces, `I`/`L`→`1`, `O`→`0`.

Enrollment is a magic link sent over WhatsApp:

```
https://seminarios.slippi.org/#t=K7RM-9XQ2-4TBV-8HNC
```

The `#` fragment is **never transmitted to a server**, so the token lands in neither
GitHub Pages' nor Cloudflare's logs. Do not "fix" this into `?t=`.

## 🗺️ API

Base `https://seminarios-api.slippi.org/api/v1`, `Authorization: Bearer <token>` on
everything except `/healthz`.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/healthz` | unauthenticated; DB ping for the compose health check |
| `GET` | `/me` | player, role, characters, server time |
| `GET` | `/roster` | every player's name and every character's name/colour, for attribution; inactive rows flagged, not hidden |
| `GET` | `/state?since=&scope=` | delta sync; tombstones included when `since` is given |
| `POST` `PATCH` `DELETE` | `/events`, `/events/{id}` | |
| `POST` `PATCH` `DELETE` | `/notes`, `/notes/{id}` | |
| `GET` `PUT` | `/settings` | shared `era` / `campaignStart` / `today`; `PUT` is gm/admin |

Three rules the code enforces everywhere, not per-route:

- **The author is the token.** Any author field in a request body is ignored silently.
- **Visibility is one predicate** (`app/access.py`), used by every read path. `player`
  sees `party` and `public`; `gm` and `admin` see everything.
- **Deletes are soft.** Nothing in a memorial is ever hard-deleted; `deleted_at` plus git
  history is the record.

Text is stored and returned as **plain text** and never interpreted. The client renders
with `textContent`, never `innerHTML` — that, not input filtering, is the defense against
a pasted `<script>`.

## 🧱 Layout

```
app/
  main.py      app, CORS, body-size cap, /healthz
  config.py    every knob, from the environment
  db.py        connections, PRAGMAs, schema bootstrap
  schema.sql   the tables (PLAN.md §5)
  auth.py      token generation, normalization, hashing, lookup
  access.py    ← the only place visibility and permission are decided
  store.py     queries and row serialization
  limits.py    per-token write and per-IP failed-auth windows
  deps.py      FastAPI dependencies
  routes/      me, roster, state, events, notes, settings
manage.py      player/character CLI
tests/         67 tests, weighted toward visibility and auth
```

## 🐳 Deployment

The compose service block, the Cloudflare tunnel, and the backup/export scripts live in
`gitility`, not here. Two things that bite:

- Compose runs from `/home/aaron/docker`, whose `docker-compose.yml` is a symlink into
  the Pi's gitility checkout. `git pull` there updates the live file; never copy over it.
- Create `~/docker/seminarios/data` as `aaron` before the first `compose up`, or Docker
  creates it as root and the container cannot write the database.
- The database is a bind mount, so the container runs as uid 1000 to match `aaron` on
  `ag-rpi5`. Change one and you must change the other.

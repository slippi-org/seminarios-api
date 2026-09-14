"""Environment configuration. Every knob is an env var so the container is the
only place deployment facts live (PLAN.md §4: nothing about deployment in this repo)."""
import os


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


DB_PATH = os.environ.get("SEM_DB_PATH", "data/seminarios.sqlite")

# Exact origins, never "*" -- the API is authenticated (PLAN.md §8).
CORS_ORIGINS = [
    o.strip() for o in os.environ.get(
        "SEM_CORS_ORIGINS", "https://seminarios.slippi.org"
    ).split(",") if o.strip()
]

# v1 ships false. Flipping it on later opens visibility='public' rows to
# unauthenticated readers -- a config change, not a code change.
PUBLIC_READ = _bool("SEM_PUBLIC_READ", False)

SITE_BASE_URL = os.environ.get("SEM_SITE_BASE_URL", "https://seminarios.slippi.org")
DEFAULT_SCOPE = os.environ.get("SEM_DEFAULT_SCOPE", "seminarios")

# Limits (PLAN.md §6). All enforced server-side; mirrored at the Cloudflare edge.
MAX_BODY_BYTES = _int("SEM_MAX_BODY_BYTES", 64 * 1024)
MAX_EVENT_TEXT = _int("SEM_MAX_EVENT_TEXT", 4_000)
MAX_NOTE_TEXT = _int("SEM_MAX_NOTE_TEXT", 20_000)
WRITES_PER_MIN = _int("SEM_WRITES_PER_MIN", 60)
WRITES_PER_DAY = _int("SEM_WRITES_PER_DAY", 500)
FAILED_AUTH_PER_MIN = _int("SEM_FAILED_AUTH_PER_MIN", 10)

# Row count past which something is wrong (a bug signal, not capacity).
ROW_COUNT_ALERT = _int("SEM_ROW_COUNT_ALERT", 50_000)

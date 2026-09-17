"""Seminarios API.

A small authenticated event/note log for the Free City of Seminarios map.
See PLAN.md in leependu/gitility for the architecture this implements.
"""
import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, db
from .deps import get_conn
from .routes import events, me, notes, roster, settings, state

API_PREFIX = "/api/v1"

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Apply the schema on startup. Idempotent, so a restart is always safe."""
    db.init()
    yield


app = FastAPI(
    title="Seminarios API",
    version="0.1.0",
    description="Authenticated event and note log for seminarios.slippi.org",
    lifespan=lifespan,
)

# Exact origins, never "*": the API is authenticated, so a wildcard origin plus
# credentials is both refused by browsers and wrong in principle (PLAN.md §8).
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Reject oversized bodies on the declared length, before reading them."""
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > config.MAX_BODY_BYTES:
                return JSONResponse(
                    {"detail": f"request body exceeds {config.MAX_BODY_BYTES} bytes"},
                    status_code=413,
                )
        except ValueError:
            return JSONResponse({"detail": "bad content-length"}, status_code=400)
    return await call_next(request)


@app.get("/healthz")
def healthz(conn: sqlite3.Connection = Depends(get_conn)):
    """Unauthenticated DB ping. Used by the compose health check (PLAN.md §8)."""
    try:
        conn.execute("SELECT 1 FROM players LIMIT 1").fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(503, f"database unavailable: {exc}")
    return {"status": "ok"}


for module in (me, roster, state, events, notes, settings):
    app.include_router(module.router, prefix=API_PREFIX)

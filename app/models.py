"""Request/response shapes.

Note what is absent: no request model carries an author field. Authorship comes
from the token, server-side, always (PLAN.md §6). A body that contains one is
ignored silently, which `extra="ignore"` (pydantic's default) gives us.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import config

TimeOfDay = Literal["morning", "midday", "afternoon", "evening", "night"]
Visibility = Literal["gm", "party", "public"]

# Client-generated ids (PLAN.md §5) so a retried POST is idempotent on replay.
ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class EventCreate(BaseModel):
    id: str = Field(pattern=ID_PATTERN)
    scope: str = Field(default=config.DEFAULT_SCOPE, max_length=64)
    place_id: str | None = Field(default=None, max_length=128)
    place: str | None = Field(default=None, max_length=200)
    day: int
    time_of_day: TimeOfDay | None = None
    text: str = Field(min_length=1, max_length=config.MAX_EVENT_TEXT)
    character_id: str | None = Field(default=None, pattern=ID_PATTERN)
    visibility: Visibility = "party"

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


class EventPatch(BaseModel):
    place_id: str | None = Field(default=None, max_length=128)
    place: str | None = Field(default=None, max_length=200)
    day: int | None = None
    time_of_day: TimeOfDay | None = None
    text: str | None = Field(default=None, min_length=1, max_length=config.MAX_EVENT_TEXT)
    character_id: str | None = Field(default=None, pattern=ID_PATTERN)
    visibility: Visibility | None = None


class NoteCreate(BaseModel):
    id: str = Field(pattern=ID_PATTERN)
    scope: str = Field(default=config.DEFAULT_SCOPE, max_length=64)
    place_id: str | None = Field(default=None, max_length=128)
    text: str = Field(min_length=1, max_length=config.MAX_NOTE_TEXT)
    visibility: Visibility = "party"


class NotePatch(BaseModel):
    place_id: str | None = Field(default=None, max_length=128)
    text: str | None = Field(default=None, min_length=1, max_length=config.MAX_NOTE_TEXT)
    visibility: Visibility | None = None


class SettingsPut(BaseModel):
    """Partial: only the keys present are written. gm/admin only."""
    scope: str = Field(default=config.DEFAULT_SCOPE, max_length=64)
    era: str | None = Field(default=None, max_length=64)
    campaignStart: int | None = None
    today: int | None = None

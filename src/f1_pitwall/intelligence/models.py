"""Normalized F1 calendar, classification, standings and news contracts."""

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl, field_validator

from f1_pitwall.domain.models import FrozenModel


class Person(FrozenModel):
    driver_id: str
    full_name: str
    abbreviation: str | None = None
    nationality: str | None = None


class Team(FrozenModel):
    team_id: str
    name: str
    nationality: str | None = None


class SessionTime(FrozenModel):
    event_id: str
    name: str
    day: date
    starts_at: AwareDatetime | None = None

    @field_validator("starts_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value else None


class Event(FrozenModel):
    event_id: str
    season: int
    round_number: int
    name: str
    circuit_id: str
    circuit_name: str
    country: str
    race_date: date
    sessions: tuple[SessionTime, ...]
    source: str = "Jolpica"

    @property
    def race_start(self) -> datetime | None:
        return next((s.starts_at for s in self.sessions if s.name == "Race"), None)


class Classification(FrozenModel):
    position: int | None = None
    driver: Person
    team: Team
    grid_position: int | None = None
    points: float | None = None
    laps: int | None = None
    status: str | None = None
    q1: str | None = None
    q2: str | None = None
    q3: str | None = None


class Grid(FrozenModel):
    event_id: str
    source: Literal["race_result", "provisional_qualifying"]
    entries: tuple[Classification, ...]
    warning: str | None = None


class Standing(FrozenModel):
    position: int
    points: float
    wins: int
    season: int
    round_number: int
    driver: Person | None = None
    teams: tuple[Team, ...] = ()


class NewsItem(FrozenModel):
    headline: str
    source: str
    url: HttpUrl
    published_at: AwareDatetime | None = None
    snippet: str | None = Field(default=None, max_length=300)
    category: str = "GENERAL"
    driver_tags: tuple[str, ...] = ()
    team_tags: tuple[str, ...] = ()
    event_tags: tuple[str, ...] = ()


class NewsFeed(FrozenModel):
    items: tuple[NewsItem, ...]
    warnings: tuple[str, ...] = ()

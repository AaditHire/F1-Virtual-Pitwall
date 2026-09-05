"""Calendar selection and upcoming-race assembly over normalized provider models."""

from datetime import UTC, datetime, timedelta
from typing import Protocol

from f1_pitwall.intelligence.models import Event, Grid, SessionTime
from f1_pitwall.intelligence.provider import IntelligenceProvider
from f1_pitwall.simulation.models import Entrant, PreRaceRequest, RaceRules


class QualifyingEntrantsProvider(Protocol):
    def qualifying_entrants(
        self, year: int, event: int, as_of: datetime
    ) -> tuple[Entrant, ...]: ...


class IntelligenceService:
    def __init__(
        self,
        provider: IntelligenceProvider,
        qualifying_provider: QualifyingEntrantsProvider | None = None,
    ) -> None:
        self.provider = provider
        self.qualifying_provider = qualifying_provider

    def upcoming_calendar(self, now: datetime) -> tuple[Event, ...]:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return tuple(
            event
            for year in self.provider.seasons()
            if year >= now.year
            for event in self.provider.calendar(year)
        )

    def next_event(self, now: datetime) -> Event | None:
        return min(
            (
                event
                for event in self.upcoming_calendar(now)
                if event.race_start is not None and event.race_start > now
            ),
            key=lambda event: event.race_start or datetime.max.replace(tzinfo=UTC),
            default=None,
        )

    def next_session(self, now: datetime) -> SessionTime | None:
        return min(
            (
                session
                for event in self.upcoming_calendar(now)
                for session in event.sessions
                if session.starts_at is not None and session.starts_at > now
            ),
            key=lambda session: session.starts_at or datetime.max.replace(tzinfo=UTC),
            default=None,
        )

    def current_event(self, now: datetime) -> Event | None:
        # A weekend selection, not a live race-status claim. Four hours is a display window.
        return next(
            (
                event
                for event in self.upcoming_calendar(now)
                if event.race_start is not None
                and min(session.day for session in event.sessions) <= now.date()
                and now <= event.race_start + timedelta(hours=4)
            ),
            None,
        )

    def grid(self, year: int, round_number: int) -> Grid:
        results = self.provider.classifications(year, round_number)
        if results:
            return Grid(
                event_id=f"{year}-{round_number}",
                source="race_result",
                entries=tuple(sorted(results, key=lambda row: row.grid_position or 999)),
            )
        qualifying = self.provider.classifications(year, round_number, "qualifying")
        return Grid(
            event_id=f"{year}-{round_number}",
            source="provisional_qualifying",
            entries=qualifying,
            warning="Qualifying order only; penalties are not applied.",
        )

    def next_race_request(
        self, now: datetime, total_laps: int, rules: RaceRules | None = None
    ) -> PreRaceRequest:
        event = self.next_event(now)
        if event is None or event.race_start is None:
            raise ValueError("No future event with a confirmed race start is available")
        if self.qualifying_provider is not None:
            entrants = list(
                self.qualifying_provider.qualifying_entrants(event.season, event.round_number, now)
            )
            return PreRaceRequest(
                event_id=event.event_id,
                race_start=event.race_start,
                as_of=now,
                total_laps=total_laps,
                entrants=tuple(entrants),
                rules=rules or RaceRules(),
                grid_source="provisional_qualifying",
            )
        qualifying = self.provider.classifications(event.season, event.round_number, "qualifying")
        if not qualifying:
            raise ValueError(
                "Qualifying not available; supply a pre-race state with entrant assumptions"
            )
        entrants = []
        for row in qualifying:
            times = [value for value in (row.q1, row.q2, row.q3) if value and ":" in value]
            pace = min(
                (
                    int(value.split(":")[0]) * 60000 + float(value.split(":")[1]) * 1000
                    for value in times
                ),
                default=90000,
            )
            entrants.append(
                Entrant(
                    driver_id=row.driver.driver_id,
                    team_id=row.team.team_id,
                    grid_position=row.position or 0,
                    base_pace_ms=pace * 1.04,
                    confidence=0.2,
                    pace_sigma_ms=1200,
                )
            )
        return PreRaceRequest(
            event_id=event.event_id,
            race_start=event.race_start,
            as_of=now,
            total_laps=total_laps,
            entrants=tuple(entrants),
            rules=rules or RaceRules(),
            grid_source="provisional_qualifying",
        )

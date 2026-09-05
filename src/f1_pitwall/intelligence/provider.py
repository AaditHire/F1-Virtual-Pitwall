"""Cached, paginated Jolpica adapter. Provider shapes stop at this boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime
from time import monotonic
from typing import Any, Protocol

import httpx

from f1_pitwall.intelligence.models import (
    Classification,
    Event,
    Person,
    SessionTime,
    Standing,
    Team,
)


class ProviderUnavailableError(RuntimeError):
    """A configured data provider failed; never substitute invented current facts."""


class IntelligenceProvider(Protocol):
    def seasons(self) -> tuple[int, ...]: ...
    def drivers(self, year: int) -> tuple[Person, ...]: ...
    def teams(self, year: int) -> tuple[Team, ...]: ...
    def calendar(self, year: int) -> tuple[Event, ...]: ...
    def classifications(
        self, year: int, round_number: int, kind: str = "results"
    ) -> tuple[Classification, ...]: ...
    def standings(self, year: int, constructors: bool = False) -> tuple[Standing, ...]: ...


def _person(item: dict[str, Any]) -> Person:
    return Person(
        driver_id=item["driverId"],
        full_name=f"{item['givenName']} {item['familyName']}",
        abbreviation=item.get("code"),
        nationality=item.get("nationality"),
    )


def _team(item: dict[str, Any]) -> Team:
    return Team(
        team_id=item["constructorId"], name=item["name"], nationality=item.get("nationality")
    )


def _extract(value: Any, path: tuple[str, ...]) -> list[dict[str, Any]]:
    if not path:
        return list(value) if isinstance(value, list) else [value]
    if isinstance(value, list):
        return [row for item in value for row in _extract(item, path)]
    return _extract(value[path[0]], path[1:])


class JolpicaProvider:
    """Bounded TTL cache and provider pagination; HTTP failures are explicit and retryable."""

    def __init__(
        self,
        base_url: str = "https://api.jolpi.ca/ergast/f1",
        client: httpx.Client | None = None,
        ttl_seconds: float = 300,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(
            timeout=20, headers={"User-Agent": "F1VirtualPitWall/0.2"}
        )
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def close(self) -> None:
        self.client.close()

    def _get(self, endpoint: str, offset: int) -> dict[str, Any]:
        key = f"{endpoint}:{offset}"
        cached = self._cache.get(key)
        if cached and monotonic() - cached[0] < self.ttl_seconds:
            return cached[1]
        try:
            response = self.client.get(
                f"{self.base_url}/{endpoint.strip('/')}/",
                params={"limit": 100, "offset": offset},
                headers={"User-Agent": "F1VirtualPitWall/0.2"},
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()["MRData"]
            if len(self._cache) >= 256:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (monotonic(), payload)
            return payload
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise ProviderUnavailableError(
                "Jolpica unavailable or returned invalid data."
            ) from error

    def _rows(self, endpoint: str, path: tuple[str, ...]) -> list[dict[str, Any]]:
        result = []
        offset = 0
        try:
            while True:
                payload = self._get(endpoint, offset)
                batch = _extract(payload, path)
                result.extend(batch)
                limit = int(payload["limit"])
                if limit <= 0:
                    raise ValueError("invalid pagination limit")
                offset += limit
                if offset >= int(payload["total"]):
                    break
                if not batch or offset > 100000:
                    raise ValueError("incomplete provider pagination")
        except (ValueError, KeyError, TypeError) as error:
            raise ProviderUnavailableError("Jolpica response contract changed.") from error
        return result

    def seasons(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                int(row["season"])
                for row in self._rows("seasons", ("SeasonTable", "Seasons"))
                if int(row["season"]) >= 2021
            )
        )

    def drivers(self, year: int) -> tuple[Person, ...]:
        return tuple(
            _person(row) for row in self._rows(f"{year}/drivers", ("DriverTable", "Drivers"))
        )

    def teams(self, year: int) -> tuple[Team, ...]:
        return tuple(
            _team(row)
            for row in self._rows(f"{year}/constructors", ("ConstructorTable", "Constructors"))
        )

    def calendar(self, year: int) -> tuple[Event, ...]:
        events = []
        for row in self._rows(f"{year}/races", ("RaceTable", "Races")):
            event_id = f"{row['season']}-{row['round']}"
            sessions = []
            # Any named date/time object is a session, including new sprint formats.
            schedule = {"Race": {"date": row["date"], "time": row.get("time")}}
            schedule.update(
                {
                    key: value
                    for key, value in row.items()
                    if isinstance(value, dict) and "date" in value
                }
            )
            for name, value in schedule.items():
                starts_at = (
                    datetime.fromisoformat(f"{value['date']}T{value['time']}").astimezone(UTC)
                    if value.get("time")
                    else None
                )
                sessions.append(
                    SessionTime(
                        event_id=event_id,
                        name=name,
                        day=date.fromisoformat(value["date"]),
                        starts_at=starts_at,
                    )
                )
            circuit = row["Circuit"]
            events.append(
                Event(
                    event_id=event_id,
                    season=int(row["season"]),
                    round_number=int(row["round"]),
                    name=row["raceName"],
                    circuit_id=circuit["circuitId"],
                    circuit_name=circuit["circuitName"],
                    country=circuit["Location"]["country"],
                    race_date=date.fromisoformat(row["date"]),
                    sessions=tuple(
                        sorted(
                            sessions,
                            key=lambda item: (
                                item.day,
                                item.starts_at or datetime.max.replace(tzinfo=UTC),
                            ),
                        )
                    ),
                )
            )
        return tuple(events)

    def classifications(
        self, year: int, round_number: int, kind: str = "results"
    ) -> tuple[Classification, ...]:
        keys = {"results": "Results", "qualifying": "QualifyingResults", "sprint": "SprintResults"}
        if kind not in keys:
            raise ValueError("unsupported classification kind")
        rows = self._rows(f"{year}/{round_number}/{kind}", ("RaceTable", "Races", keys[kind]))
        return tuple(
            Classification(
                position=int(row["position"]) if row.get("position") else None,
                driver=_person(row["Driver"]),
                team=_team(row["Constructor"]),
                grid_position=int(row["grid"]) if row.get("grid") is not None else None,
                points=float(row["points"]) if "points" in row else None,
                laps=int(row["laps"]) if "laps" in row else None,
                status=row.get("status"),
                q1=row.get("Q1"),
                q2=row.get("Q2"),
                q3=row.get("Q3"),
            )
            for row in rows
        )

    def standings(self, year: int, constructors: bool = False) -> tuple[Standing, ...]:
        key = "ConstructorStandings" if constructors else "DriverStandings"
        lists = self._rows(f"{year}/{key.lower()}", ("StandingsTable", "StandingsLists"))
        return tuple(
            Standing(
                position=int(row["position"]),
                points=float(row["points"]),
                wins=int(row["wins"]),
                season=int(group["season"]),
                round_number=int(group["round"]),
                driver=None if constructors else _person(row["Driver"]),
                teams=(_team(row["Constructor"]),)
                if constructors
                else tuple(_team(team) for team in row["Constructors"]),
            )
            for group in lists
            for row in group[key]
        )

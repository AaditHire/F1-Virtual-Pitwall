from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from f1_pitwall.intelligence.news import RssNewsProvider
from f1_pitwall.intelligence.provider import JolpicaProvider, ProviderUnavailableError
from f1_pitwall.intelligence.service import IntelligenceService


def person(index: int = 1) -> dict[str, str]:
    return {
        "driverId": f"stable-driver-{index}",
        "givenName": "Driver",
        "familyName": str(index),
        "code": f"X{index}",
        "nationality": "Test",
    }


def team() -> dict[str, str]:
    return {"constructorId": "stable-team", "name": "Team", "nationality": "Test"}


def race(year: int = 2026, round_number: int = 1) -> dict[str, Any]:
    return {
        "season": str(year),
        "round": str(round_number),
        "raceName": "Example Grand Prix",
        "Circuit": {
            "circuitId": "example",
            "circuitName": "Example",
            "Location": {"country": "UK"},
        },
        "date": f"{year}-09-06",
        "time": "14:00:00Z",
        "FirstPractice": {"date": f"{year}-09-04", "time": "10:00:00Z"},
        "SprintQualifying": {"date": f"{year}-09-04", "time": "14:00:00Z"},
        "Sprint": {"date": f"{year}-09-05", "time": "10:00:00Z"},
        "Qualifying": {"date": f"{year}-09-05", "time": "14:00:00Z"},
        "FutureSession": {"date": f"{year}-09-03"},
    }


def transport(request: httpx.Request) -> httpx.Response:
    parts = request.url.path.strip("/").split("/")
    endpoint = parts[-1]
    year = int(parts[2]) if len(parts) > 3 and parts[2].isdigit() else 2026
    payload: dict[str, Any] = {"total": "1", "limit": "100"}
    if endpoint == "seasons":
        payload["SeasonTable"] = {
            "Seasons": [{"season": str(y)} for y in (2020, 2021, 2023, 2026, 2027)]
        }
    elif endpoint == "drivers":
        payload["DriverTable"] = {"Drivers": [person(i) for i in range(24)]}
    elif endpoint == "constructors":
        payload["ConstructorTable"] = {"Constructors": [team()]}
    elif endpoint == "races":
        payload["RaceTable"] = {"Races": [race(year)]}
    elif endpoint in {"results", "qualifying", "sprint"}:
        keys = {"results": "Results", "qualifying": "QualifyingResults", "sprint": "SprintResults"}
        result: dict[str, Any] = {
            "Driver": person(),
            "Constructor": team(),
            "position": "1",
            "grid": "0",
            "points": "25",
            "laps": "50",
            "status": "Finished",
            "Q1": "1:30.000",
        }
        payload["RaceTable"] = {"Races": [{**race(year), keys[endpoint]: [result]}]}
    else:
        key = "ConstructorStandings" if endpoint == "constructorstandings" else "DriverStandings"
        result = {
            "position": "1",
            "points": "42",
            "wins": "1",
            "Driver": person(),
            "Constructors": [team()],
            "Constructor": team(),
        }
        payload["StandingsTable"] = {
            "StandingsLists": [{"season": str(year), "round": "2", key: [result]}]
        }
    return httpx.Response(200, json={"MRData": payload})


def provider() -> JolpicaProvider:
    return JolpicaProvider(client=httpx.Client(transport=httpx.MockTransport(transport)))


@pytest.mark.parametrize("year", [2021, 2023, 2026, 2027])
def test_dynamic_seasons_grids_and_sprint_calendar(year: int) -> None:
    source = provider()
    assert source.seasons() == (2021, 2023, 2026, 2027)
    assert len(source.drivers(year)) == 24
    assert source.teams(year)[0].team_id == "stable-team"
    event = source.calendar(year)[0]
    assert event.season == year
    assert event.race_start
    assert event.race_start.tzinfo == UTC
    assert {session.name for session in event.sessions} >= {"SprintQualifying", "FutureSession"}
    assert next(s for s in event.sessions if s.name == "FutureSession").starts_at is None
    for kind in ("results", "qualifying", "sprint"):
        assert source.classifications(year, 1, kind)[0].driver.driver_id == "stable-driver-1"
    assert source.standings(year)[0].round_number == 2
    assert source.standings(year, True)[0].teams[0].team_id == "stable-team"
    source.close()


def test_pagination_cache_and_provider_failure_are_explicit() -> None:
    calls = []

    def paged(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        offset = int(request.url.params["offset"])
        return httpx.Response(
            200,
            json={
                "MRData": {
                    "total": "3",
                    "limit": "2",
                    "DriverTable": {
                        "Drivers": [person(i) for i in range(offset, min(offset + 2, 3))]
                    },
                }
            },
        )

    source = JolpicaProvider(client=httpx.Client(transport=httpx.MockTransport(paged)))
    assert len(source.drivers(2026)) == 3
    assert len(source.drivers(2026)) == 3
    assert len(calls) == 2
    for status in (429, 500):
        failed = JolpicaProvider(
            client=httpx.Client(
                transport=httpx.MockTransport(lambda request, code=status: httpx.Response(code))
            )
        )
        with pytest.raises(ProviderUnavailableError):
            failed.seasons()
    broken = JolpicaProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"MRData": {"limit": 0, "total": 1, "DriverTable": {"Drivers": []}}}
                )
            )
        )
    )
    with pytest.raises(ProviderUnavailableError, match="contract"):
        broken.drivers(2026)
    with pytest.raises(ValueError, match="unsupported"):
        source.classifications(2026, 1, "other")


def test_calendar_crosses_season_boundary_and_pre_race_never_reads_results() -> None:
    source = provider()
    service = IntelligenceService(source)
    now = datetime(2026, 9, 5, 16, tzinfo=UTC)
    assert service.current_event(now)
    event = service.next_event(now)
    assert event
    assert event.season == 2026
    session = service.next_session(now)
    assert session
    assert session.name == "Race"
    after = datetime(2026, 12, 31, tzinfo=UTC)
    future = service.next_event(after)
    assert future
    assert future.season == 2027
    assert service.next_event(datetime(2028, 1, 1, tzinfo=UTC)) is None
    request = service.next_race_request(now, 57)
    assert request.grid_source == "provisional_qualifying"
    assert request.entrants[0].base_pace_ms == 93600
    assert service.grid(2026, 1).source == "race_result"
    with pytest.raises(ValueError, match="timezone"):
        service.next_event(datetime(2026, 1, 1))  # noqa: DTZ001
    with pytest.raises(ValueError, match="No future"):
        service.next_race_request(datetime(2028, 1, 1, tzinfo=UTC), 57)


def test_missing_qualifying_grid_and_unpublished_next_race() -> None:
    def missing(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(("results/", "qualifying/")):
            return httpx.Response(
                200, json={"MRData": {"total": "0", "limit": "100", "RaceTable": {"Races": []}}}
            )
        return transport(request)

    source = JolpicaProvider(client=httpx.Client(transport=httpx.MockTransport(missing)))
    service = IntelligenceService(source)
    assert service.grid(2026, 1).warning
    with pytest.raises(ValueError, match="Qualifying not available"):
        service.next_race_request(datetime(2026, 9, 5, tzinfo=UTC), 57)


def test_news_deduplicates_sanitizes_and_tags_short_metadata() -> None:
    xml = b"""<rss><channel>
    <item><title>Driver 1 takes pole</title><link>https://example.com/story?utm_source=test</link>
    <pubDate>Sat, 05 Sep 2026 14:00:00 GMT</pubDate>
    <description>&lt;b&gt;Short snippet&lt;/b&gt;</description></item>
    <item><title>Driver 1 takes pole!</title><link>https://another.com/copy</link></item>
    <item><title>Broken link</title><link>javascript:alert(1)</link></item>
    <item><title>Team upgrade</title><link>https://example.com/upgrade</link><pubDate>bad</pubDate></item>
    </channel></rss>"""
    calls = []

    def rss(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, content=xml)

    news = RssNewsProvider(
        ("https://example.com/rss",),
        client=httpx.Client(transport=httpx.MockTransport(rss)),
        tags={"driver": {"Driver 1": "stable-driver-1"}},
    )
    result = news.latest(1)
    assert result.items[0].driver_tags == ("stable-driver-1",)
    assert result.items[0].snippet == "Short snippet"
    assert result.items[0].category == "QUALIFYING"
    assert str(result.items[0].url) == "https://example.com/story"
    assert len(news.latest(20).items) == 2
    assert len(calls) == 1
    news.close()
    assert RssNewsProvider().latest().warnings
    with pytest.raises(ValueError, match="limit"):
        RssNewsProvider().latest(0)


@pytest.mark.parametrize(
    "content",
    [b"invalid XML", b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss>&x;</rss>', b"x" * 2_000_001],
    ids=["malformed", "entity", "oversized"],
)
def test_broken_or_unsafe_feed_fails_gracefully(content: bytes) -> None:
    news = RssNewsProvider(
        ("https://example.com/rss",),
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content))
        ),
    )
    assert news.latest().warnings


def test_atom_feed_and_missing_timestamp() -> None:
    xml = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Race news</title>
    <link href="https://example.com/atom"/><published>2026-09-05T10:00:00Z</published>
    <summary>Brief summary</summary></entry></feed>"""
    news = RssNewsProvider(
        ("https://example.com/rss",),
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=xml))
        ),
    )
    assert news.latest().items[0].published_at == datetime(2026, 9, 5, 10, tzinfo=UTC)


def test_complete_qualifying_provider_takes_priority_over_partial_classification() -> None:
    from f1_pitwall.simulation.models import Entrant

    class CompleteQualifying:
        def qualifying_entrants(
            self, year: int, event: int, as_of: datetime
        ) -> tuple[Entrant, ...]:
            return tuple(
                Entrant(driver_id=f"complete-{i}", grid_position=i + 1, base_pace_ms=90000)
                for i in range(22)
            )

    service = IntelligenceService(provider(), CompleteQualifying())
    request = service.next_race_request(datetime(2026, 9, 5, 18, tzinfo=UTC), 57)
    assert len(request.entrants) == 22

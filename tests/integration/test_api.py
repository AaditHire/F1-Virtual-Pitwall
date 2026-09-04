from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from f1_pitwall.api import create_app
from f1_pitwall.config import Settings
from f1_pitwall.weather import OpenMeteoClient
from f1_pitwall.weather.open_meteo import WeatherObservation


def test_http_replay_flow(fixture_path: Path, tmp_path: Path) -> None:
    app = create_app(Settings(fixture_path=fixture_path, knowledge_db=tmp_path / "knowledge.db"))
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        session = client.get("/api/v1/session")
        assert session.status_code == 200
        assert len(session.json()["drivers"]) == 6
        snapshot = client.get("/api/v1/snapshot/12")
        assert snapshot.status_code == 200
        assert snapshot.headers["x-request-id"]
        strategy = client.get("/api/v1/strategy/NOR/12")
        assert strategy.status_code == 200
        assert strategy.json()["max_source_lap"] <= 12
        laps = client.get("/api/v1/lap-times/12?drivers=NOR,RUS")
        assert {item["driver_id"] for item in laps.json()} == {"NOR", "RUS"}
        assert client.get("/api/v1/lap-times/99").status_code == 422
        tyres = client.get("/api/v1/tyres/NOR/12")
        assert tyres.status_code == 200
        assert tyres.json()["max_source_lap"] <= 12
        traffic = client.get("/api/v1/traffic/NOR/12")
        assert traffic.status_code == 200
        assert traffic.json()["max_source_lap"] <= 12
        trace = client.get("/api/v1/trace/NOR/12")
        assert trace.status_code == 200
        assert trace.json()["max_source_lap"] <= 12
        assert all(result["passed"] for result in client.get("/api/v1/evaluations").json())
        assert client.get("/api/v1/capabilities").json()["weather"] == "ready"


def test_http_validation_and_optional_agent(fixture_path: Path, tmp_path: Path) -> None:
    app = create_app(Settings(fixture_path=fixture_path, knowledge_db=tmp_path / "knowledge.db"))
    with TestClient(app) as client:
        assert client.get("/api/v1/snapshot/99").status_code == 422
        assert client.post("/api/v1/radio/classify", json={"text": "Box, box"}).status_code == 200
        knowledge = client.get("/api/v1/knowledge/search", params={"query": "strategy"})
        assert knowledge.status_code == 200
        assert knowledge.json()[0]["title"] == "Race Strategy Principles"
        response = client.post(
            "/api/v1/agent/advice",
            json={"lap": 12, "driver_id": "NOR", "question": "Pit now?"},
        )
        assert response.status_code == 503


def test_http_weather_adapter(
    fixture_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_day(
        self: OpenMeteoClient,
        *,
        latitude: float,
        longitude: float,
        day: date,
    ) -> tuple[WeatherObservation, ...]:
        assert latitude == 26.0325
        assert longitude == 50.5106
        assert day == date(2024, 3, 2)
        return (
            WeatherObservation(
                observed_at=datetime(2024, 3, 2, 12, tzinfo=UTC),
                temperature_c=23.5,
                precipitation_mm=0.0,
                wind_speed_kmh=18.0,
            ),
        )

    monkeypatch.setattr(OpenMeteoClient, "fetch_day", fake_fetch_day)
    app = create_app(Settings(fixture_path=fixture_path, knowledge_db=tmp_path / "knowledge.db"))
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/weather",
            params={"latitude": 26.0325, "longitude": 50.5106, "day": "2024-03-02"},
        )
        assert response.status_code == 200
        assert response.json()[0]["temperature_c"] == 23.5

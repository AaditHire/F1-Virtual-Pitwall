from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from f1_pitwall.api import create_app
from f1_pitwall.config import Settings
from f1_pitwall.intelligence.provider import JolpicaProvider
from f1_pitwall.intelligence.service import IntelligenceService
from f1_pitwall.simulation.models import Entrant, PreRaceRequest, SimulationRequest
from tests.unit.test_intelligence import provider


def test_full_grid_and_pre_race_http_flow(tmp_path: Path) -> None:
    app = create_app(Settings(knowledge_db=tmp_path / "knowledge.db"))
    with TestClient(app) as client:
        count = len(client.get("/api/v1/session").json()["drivers"])
        all_drivers = client.get("/api/v1/strategies/12?simulations=3")
        assert all_drivers.status_code == 200
        assert len(all_drivers.json()["predictions"]) == count
        assert client.get("/api/v1/strategies/12/D001?simulations=3").status_code == 200
        assert client.get("/api/v1/pit-loss/18").status_code == 200
        assert client.get("/api/v1/evaluations/historical/12?simulations=3").status_code == 200
        assert client.get("/api/v1/strategies/12?simulations=5001").status_code == 422
        assert client.get("/api/v1/strategies/30").status_code == 422
        assert client.get("/api/v1/news").json()["warnings"]
        now = datetime(2026, 9, 5, tzinfo=UTC)
        request = PreRaceRequest(
            event_id="future",
            as_of=now,
            race_start=now + timedelta(days=1),
            total_laps=30,
            entrants=tuple(
                Entrant(driver_id=f"future-{i}", grid_position=i + 1, base_pace_ms=90000 + i * 100)
                for i in range(12)
            ),
        )
        state = client.post(
            "/api/v1/simulation/pre-race-state", json=request.model_dump(mode="json")
        )
        assert state.status_code == 200
        payload = {"state": state.json(), "simulations": 5, "seed": 7}
        prediction = client.post("/api/v1/simulation/race", json=payload)
        assert prediction.status_code == 200
        assert len(prediction.json()["predictions"]) == 12
        assert prediction.json() == client.post("/api/v1/simulation/race", json=payload).json()
        assert SimulationRequest.model_validate(payload).seed == 7
        assert client.get("/openapi.json").status_code == 200


def test_intelligence_http_routes_and_provider_failure(tmp_path: Path) -> None:
    app = create_app(Settings(knowledge_db=tmp_path / "knowledge.db"))
    with TestClient(app) as client:
        app.state.intelligence = IntelligenceService(provider())
        routes = [
            "seasons",
            "seasons/2026/drivers",
            "seasons/2026/teams",
            "seasons/2026/calendar",
            "events/current",
            "events/next",
            "sessions/next",
            "events/2026/1/qualifying",
            "events/2026/1/results",
            "events/2026/1/sprint",
            "events/2026/1/grid",
            "standings/drivers",
            "standings/constructors",
            "standings/drivers?year=2023",
            "predictions/next-race?total_laps=30&simulations=3",
        ]
        for route in routes:
            response = client.get(f"/api/v1/{route}")
            assert response.status_code == 200, response.text
        app.state.intelligence = IntelligenceService(
            JolpicaProvider(
                client=httpx.Client(
                    transport=httpx.MockTransport(lambda request: httpx.Response(429))
                )
            )
        )
        unavailable = client.get("/api/v1/seasons")
        assert unavailable.status_code == 503
        assert unavailable.headers["retry-after"] == "60"

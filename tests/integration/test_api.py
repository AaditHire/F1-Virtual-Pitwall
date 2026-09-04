from pathlib import Path

from fastapi.testclient import TestClient

from f1_pitwall.api import create_app
from f1_pitwall.config import Settings


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


def test_http_validation_and_optional_agent(
    fixture_path: Path, tmp_path: Path, monkeypatch: object
) -> None:
    app = create_app(Settings(fixture_path=fixture_path, knowledge_db=tmp_path / "knowledge.db"))
    with TestClient(app) as client:
        assert client.get("/api/v1/snapshot/99").status_code == 422
        assert client.post("/api/v1/radio/classify", json={"text": "Box, box"}).status_code == 200
        assert (
            client.get("/api/v1/knowledge/search", params={"query": "strategy"}).status_code == 200
        )
        response = client.post(
            "/api/v1/agent/advice",
            json={"lap": 12, "driver_id": "NOR", "question": "Pit now?"},
        )
        assert response.status_code == 503

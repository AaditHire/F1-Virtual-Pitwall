"""Opt-in live verification; downloaded timing and reports stay in ignored data/cache."""

import json
from datetime import UTC, datetime
from pathlib import Path

from f1_pitwall.application import PitWallService
from f1_pitwall.evaluations.historical import evaluate_historical
from f1_pitwall.ingestion import write_fixture
from f1_pitwall.ingestion.fastf1_source import FastF1Source
from f1_pitwall.intelligence.provider import JolpicaProvider
from f1_pitwall.simulation.models import PreRaceRequest
from f1_pitwall.simulation.race import simulate_race
from f1_pitwall.simulation.state import build_pre_race


def main() -> None:
    root = Path("data/cache/verification")
    root.mkdir(parents=True, exist_ok=True)
    provider = JolpicaProvider()
    years = sorted({2021, 2023, max(provider.seasons())})
    source = FastF1Source(Path("data/cache/fastf1"))
    reports: list[dict[str, object]] = []
    for year in years:
        events = [
            event
            for event in provider.calendar(year)
            if event.race_start and event.race_start < datetime.now(UTC)
        ]
        event = events[0]
        path = root / f"{year}-{event.round_number}.json"
        try:
            dataset = source.fetch(year, event.round_number)
            write_fixture(dataset, path)
            service = PitWallService(dataset)
            lap = min(12, dataset.metadata.total_laps - 1)
            snapshot = service.snapshot(lap)
            report = evaluate_historical(dataset, lap, simulations=10)
            strategies = service.full_grid_strategy(lap, 10)
            summary = {
                "season": year,
                "event": event.name,
                "entrants": len(dataset.drivers),
                "snapshot_drivers": len(snapshot.drivers),
                "strategy_drivers": len(strategies.predictions),
                "evaluation": report.model_dump(),
            }
        except Exception as error:
            summary = {"season": year, "event": event.name, "error": str(error)}
        reports.append(summary)
        print(json.dumps(summary), flush=True)
    # Real qualifying metadata, explicit assumed race pace; no target race timing is used.
    event = provider.calendar(years[-1])[0]
    from datetime import timedelta

    now = datetime.now(UTC)
    entrants = source.qualifying_entrants(event.season, event.round_number, now)
    request = PreRaceRequest(
        event_id=f"{event.event_id}-hypothetical-future-smoke",
        race_start=now + timedelta(days=1),
        as_of=now,
        total_laps=30,
        grid_source="provisional_qualifying",
        entrants=entrants,
    )
    result = simulate_race(build_pre_race(request), simulations=10)
    print(
        json.dumps(
            {
                "pre_race_drivers": len(result.predictions),
                "note": "Hypothetical future race; known roster and assumed distance",
            }
        ),
        flush=True,
    )
    (root / "report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    provider.close()


if __name__ == "__main__":
    main()

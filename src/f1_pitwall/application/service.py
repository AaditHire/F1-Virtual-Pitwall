"""Application facade shared by HTTP, MCP, CLI, and agents."""

from __future__ import annotations

from pathlib import Path

from f1_pitwall.domain import RaceDataset, RaceSnapshot, StrategyAssessment
from f1_pitwall.ingestion import create_demo_dataset, load_fixture
from f1_pitwall.replay import ReplayBuilder
from f1_pitwall.simulation import StrategyAdvisor


class PitWallService:
    """Coordinate replay and strategy use cases over one immutable dataset."""

    def __init__(self, dataset: RaceDataset) -> None:
        self.dataset = dataset
        self._replay = ReplayBuilder(dataset)
        self._strategy = StrategyAdvisor(dataset)

    @classmethod
    def from_fixture(cls, path: Path) -> PitWallService:
        """Construct from a fixture, or use the redistribution-safe demo if absent."""
        return cls(load_fixture(path) if path.exists() else create_demo_dataset())

    def snapshot(self, cutoff_lap: int) -> RaceSnapshot:
        """Get immutable race state for one completed lap."""
        return self._replay.build(cutoff_lap)

    def strategy(self, cutoff_lap: int, driver_id: str) -> StrategyAssessment:
        """Assess immediate strategy using exactly the same cutoff snapshot."""
        snapshot = self.snapshot(cutoff_lap)
        return self._strategy.assess(snapshot, driver_id.upper())

    def lap_times(
        self, cutoff_lap: int, driver_ids: set[str] | None = None
    ) -> list[dict[str, object]]:
        """Return visible lap-time series for dashboard charts."""
        selected = {driver.upper() for driver in driver_ids} if driver_ids else None
        return [
            {
                "driver_id": lap.driver_id,
                "lap_number": lap.lap_number,
                "lap_time_ms": lap.lap_time_ms,
                "compound": lap.compound,
                "stint": lap.stint,
                "source_lap": lap.source_lap,
            }
            for lap in self.dataset.laps
            if lap.lap_number <= cutoff_lap
            and lap.lap_time_ms is not None
            and (selected is None or lap.driver_id in selected)
        ]

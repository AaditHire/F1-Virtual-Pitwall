"""Application facade shared by HTTP, MCP, CLI, and agents."""

from __future__ import annotations

from pathlib import Path

from f1_pitwall.analytics import TrafficAnalyzer, TyreAnalyzer
from f1_pitwall.domain import (
    RaceDataset,
    RaceSnapshot,
    StrategyAssessment,
    TrafficAnalysis,
    TyreTrend,
)
from f1_pitwall.ingestion import create_demo_dataset, load_fixture
from f1_pitwall.replay import ReplayBuilder
from f1_pitwall.simulation import StrategyAdvisor


class PitWallService:
    """Coordinate replay and strategy use cases over one immutable dataset."""

    def __init__(self, dataset: RaceDataset) -> None:
        self.dataset = dataset
        self._replay = ReplayBuilder(dataset)
        self._strategy = StrategyAdvisor(dataset)
        self._tyres = TyreAnalyzer(dataset)
        self._traffic = TrafficAnalyzer()

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
        self._validate_cutoff(cutoff_lap)
        selected = {driver.strip().upper() for driver in driver_ids} if driver_ids else None
        if selected and (unknown := selected - self.dataset.drivers.keys()):
            raise ValueError(f"unknown drivers: {', '.join(sorted(unknown))}")
        return [
            {
                "driver_id": lap.driver_id,
                "lap_number": lap.lap_number,
                "lap_time_ms": lap.lap_time_ms,
                "compound": lap.compound,
                "stint": lap.stint,
                "source_lap": lap.source_lap,
                "is_clean": lap.is_accurate
                and not lap.pit_in
                and not lap.pit_out
                and lap.track_status in {"", "1"},
            }
            for lap in sorted(self.dataset.laps, key=lambda lap: (lap.lap_number, lap.driver_id))
            if lap.lap_number <= cutoff_lap
            and lap.lap_time_ms is not None
            and (selected is None or lap.driver_id in selected)
        ]

    def tyre_trend(self, cutoff_lap: int, driver_id: str) -> TyreTrend:
        """Estimate the selected driver's visible current-stint tyre trend."""
        self._validate_cutoff(cutoff_lap)
        return self._tyres.estimate(driver_id.upper(), cutoff_lap)

    def traffic(
        self,
        cutoff_lap: int,
        driver_id: str,
        pit_loss_ms: int = 24_000,
    ) -> TrafficAnalysis:
        """Estimate the selected driver's green-flag pit rejoin traffic."""
        return self._traffic.analyze(
            self.snapshot(cutoff_lap),
            driver_id.upper(),
            pit_loss_ms,
        )

    def _validate_cutoff(self, cutoff_lap: int) -> None:
        total_laps = self.dataset.metadata.total_laps
        if not 1 <= cutoff_lap <= total_laps:
            raise ValueError(f"cutoff_lap must be between 1 and {total_laps}")

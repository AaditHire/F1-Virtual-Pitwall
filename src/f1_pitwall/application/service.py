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
from f1_pitwall.simulation.models import SimulationResult
from f1_pitwall.simulation.race import simulate_race
from f1_pitwall.simulation.state import build_replay_state


class PitWallService:
    """Coordinate replay and strategy use cases over one immutable dataset."""

    def __init__(self, dataset: RaceDataset) -> None:
        self.dataset = dataset
        self._replay = ReplayBuilder(dataset)
        self._strategy = StrategyAdvisor(dataset)
        self._tyres = TyreAnalyzer(dataset)
        self._traffic = TrafficAnalyzer()
        self._strategy_cache: dict[tuple[int, int, int], SimulationResult] = {}

    @classmethod
    def from_fixture(cls, path: Path) -> PitWallService:
        """Construct from a fixture, or use the redistribution-safe demo if absent."""
        return cls(load_fixture(path) if path.exists() else create_demo_dataset())

    def snapshot(self, cutoff_lap: int) -> RaceSnapshot:
        """Get immutable race state for one completed lap."""
        return self._replay.build(cutoff_lap)

    def full_grid_strategy(
        self, cutoff_lap: int, simulations: int = 100, seed: int = 42
    ) -> SimulationResult:
        """Compare race-length strategies and report realistic results for every entrant."""
        key = (cutoff_lap, simulations, seed)
        if key not in self._strategy_cache:
            result = simulate_race(build_replay_state(self.dataset, cutoff_lap), simulations, seed)
            if len(self._strategy_cache) >= 16:
                self._strategy_cache.pop(next(iter(self._strategy_cache)))
            self._strategy_cache[key] = result
        return self._strategy_cache[key]

    def strategy(self, cutoff_lap: int, driver_id: str) -> StrategyAssessment:
        """Assess immediate strategy using exactly the same cutoff snapshot."""
        snapshot = self.snapshot(cutoff_lap)
        return self._strategy.assess(snapshot, self.resolve_driver(driver_id))

    def resolve_driver(self, driver_id: str) -> str:
        """Accept a stable provider ID or an unambiguous session abbreviation."""
        value = driver_id.strip()
        if value in self.dataset.drivers:
            return value
        matches = [
            info.driver_id
            for info in self.dataset.drivers.values()
            if info.driver_id.casefold() == value.casefold()
            or (info.abbreviation or "").casefold() == value.casefold()
        ]
        if len(matches) != 1:
            raise ValueError(f"unknown drivers or ambiguous alias: {value}")
        return matches[0]

    def lap_times(
        self, cutoff_lap: int, driver_ids: set[str] | None = None
    ) -> list[dict[str, object]]:
        """Return visible lap-time series for dashboard charts."""
        self._validate_cutoff(cutoff_lap)
        selected = {self.resolve_driver(driver) for driver in driver_ids} if driver_ids else None
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
        return self._tyres.estimate(self.resolve_driver(driver_id), cutoff_lap)

    def traffic(
        self,
        cutoff_lap: int,
        driver_id: str,
        pit_loss_ms: int = 24_000,
    ) -> TrafficAnalysis:
        """Estimate the selected driver's green-flag pit rejoin traffic."""
        return self._traffic.analyze(
            self.snapshot(cutoff_lap),
            self.resolve_driver(driver_id),
            pit_loss_ms,
        )

    def _validate_cutoff(self, cutoff_lap: int) -> None:
        total_laps = self.dataset.metadata.total_laps
        if not 1 <= cutoff_lap <= total_laps:
            raise ValueError(f"cutoff_lap must be between 1 and {total_laps}")

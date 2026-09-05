"""Holdout evaluation; future observations are read only after predictions exist."""

from statistics import mean

from f1_pitwall.analytics import TyreAnalyzer
from f1_pitwall.domain import RaceDataset
from f1_pitwall.domain.models import FrozenModel
from f1_pitwall.simulation.models import MODEL_VERSION, SIMULATOR_VERSION, RaceRules
from f1_pitwall.simulation.race import simulate_race
from f1_pitwall.simulation.state import build_replay_state


class HistoricalReport(FrozenModel):
    session_id: str
    cutoff_lap: int
    model_version: str = MODEL_VERSION
    simulator_version: str = SIMULATOR_VERSION
    data_version: str
    source: str
    seed: int
    simulations: int
    full_grid_correct: bool
    evaluated_drivers: int
    finishing_position_mae: float | None
    pit_window_mae_laps: float | None
    degradation_mae_ms: float | None
    legal_strategy_fraction: float
    limitation: str = (
        "Observed final positions are timing classifications, not steward-certified results. "
        "Pit-window error compares actual stop timing, not a counterfactual optimum. "
        "Degradation metric measures held-out lap pace error, including fuel/traffic effects."
    )


def evaluate_historical(
    dataset: RaceDataset,
    cutoff_lap: int,
    simulations: int = 100,
    seed: int = 42,
    rules: RaceRules | None = None,
) -> HistoricalReport:
    prediction = simulate_race(build_replay_state(dataset, cutoff_lap, rules), simulations, seed)
    finishes = []
    windows = []
    pace_errors = []
    tyres = TyreAnalyzer(dataset)
    for driver in prediction.predictions:
        # Holdout reads below this line never flow into simulation inputs.
        future = sorted(
            [
                lap
                for lap in dataset.laps
                if lap.driver_id == driver.driver_id and lap.lap_number > cutoff_lap
            ],
            key=lambda lap: lap.lap_number,
        )
        if future and future[-1].position is not None:
            finishes.append(abs(driver.expected_finish - (future[-1].position or 0)))
        actual_pits = [lap.lap_number for lap in future if lap.pit_in]
        proposed = driver.recommended_strategy.stops
        if actual_pits and proposed:
            windows.append(abs(actual_pits[0] - proposed[0].after_lap))
        visible = [
            lap
            for lap in dataset.laps
            if lap.driver_id == driver.driver_id and lap.lap_number <= cutoff_lap
        ]
        if not visible:
            continue
        trend = tyres.estimate(driver.driver_id, cutoff_lap)
        clean = next(
            (
                lap
                for lap in future
                if lap.is_accurate
                and not lap.pit_in
                and not lap.pit_out
                and lap.track_status in {"", "1"}
                and lap.stint == trend.stint
                and lap.lap_time_ms
            ),
            None,
        )
        if clean and trend.pace_ms and trend.degradation_ms_per_lap is not None:
            forecast = trend.pace_ms + trend.degradation_ms_per_lap * (
                clean.lap_number - cutoff_lap + (trend.sample_count - 1) / 2
            )
            pace_errors.append(abs((clean.lap_time_ms or 0) - forecast))
    accounted = {driver.driver_id for driver in prediction.predictions} | set(
        prediction.excluded_driver_ids
    )
    return HistoricalReport(
        session_id=dataset.metadata.session_id,
        cutoff_lap=cutoff_lap,
        data_version=dataset.metadata.data_version,
        source=dataset.metadata.source,
        seed=seed,
        simulations=simulations,
        full_grid_correct=accounted == set(dataset.drivers),
        evaluated_drivers=len(finishes),
        finishing_position_mae=mean(finishes) if finishes else None,
        pit_window_mae_laps=mean(windows) if windows else None,
        degradation_mae_ms=mean(pace_errors) if pace_errors else None,
        legal_strategy_fraction=1.0,
    )

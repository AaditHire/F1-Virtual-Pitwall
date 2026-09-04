"""Deterministic immediate strategy comparison."""

from f1_pitwall.analytics import TrafficAnalyzer, TyreAnalyzer
from f1_pitwall.domain import (
    DataQualityWarning,
    RaceDataset,
    RaceSnapshot,
    StrategyAction,
    StrategyAssessment,
    StrategyOption,
    TrafficRisk,
)


class StrategyAdvisor:
    """Compare pitting next lap with extending the current stint by one lap."""

    def __init__(self, dataset: RaceDataset) -> None:
        self._tyres = TyreAnalyzer(dataset)
        self._traffic = TrafficAnalyzer()

    def assess(
        self,
        snapshot: RaceSnapshot,
        driver_id: str,
        *,
        horizon_laps: int = 5,
        pit_loss_ms: int = 24_000,
        out_lap_penalty_ms: int = 5_000,
    ) -> StrategyAssessment:
        """Produce an auditable short-horizon comparison from visible evidence."""
        if horizon_laps < 3:
            raise ValueError("horizon_laps must be at least 3")
        trend = self._tyres.estimate(driver_id, snapshot.cutoff_lap)
        traffic = self._traffic.analyze(snapshot, driver_id, pit_loss_ms)
        warnings = list(snapshot.warnings)

        if trend.pace_ms is None:
            warnings.append(
                DataQualityWarning(
                    code="INSUFFICIENT_PACE",
                    message="No valid current-stint pace samples are available.",
                    driver_id=driver_id,
                )
            )
            return StrategyAssessment(
                session_id=snapshot.session_id,
                cutoff_lap=snapshot.cutoff_lap,
                driver_id=driver_id,
                preferred_action=StrategyAction.NO_RECOMMENDATION,
                confidence=0,
                options=(),
                evidence=("No valid current-stint lap-time sample.",),
                warnings=tuple(warnings),
                max_source_lap=max(trend.max_source_lap, traffic.max_source_lap),
            )

        degradation = max(0.0, trend.degradation_ms_per_lap or 0.0)
        fresh_pace = max(1, round(trend.pace_ms - degradation * max(1, trend.sample_count // 2)))
        current_next_lap = round(trend.pace_ms + degradation)
        pit_next = pit_loss_ms + out_lap_penalty_ms + fresh_pace * (horizon_laps - 1)
        stay_then_pit = (
            current_next_lap + pit_loss_ms + out_lap_penalty_ms + fresh_pace * (horizon_laps - 2)
        )
        traffic_penalty = {
            TrafficRisk.HIGH: 2_000,
            TrafficRisk.MEDIUM: 750,
            TrafficRisk.LOW: 0,
            TrafficRisk.UNKNOWN: 1_000,
        }[traffic.risk]
        pit_next += traffic_penalty
        best = min(pit_next, stay_then_pit)

        common_assumptions = (
            f"Green-flag pit loss fixed at {pit_loss_ms / 1000:.1f}s.",
            f"Projection horizon is {horizon_laps} laps.",
            "No safety-car or weather transition is modeled.",
        )
        options = (
            StrategyOption(
                action=StrategyAction.PIT_NEXT_LAP,
                projected_time_ms=pit_next,
                delta_to_best_ms=pit_next - best,
                predicted_rejoin_position=traffic.predicted_rejoin_position,
                traffic_risk=traffic.risk,
                assumptions=common_assumptions,
            ),
            StrategyOption(
                action=StrategyAction.STAY_OUT_ONE_LAP,
                projected_time_ms=stay_then_pit,
                delta_to_best_ms=stay_then_pit - best,
                predicted_rejoin_position=traffic.predicted_rejoin_position,
                traffic_risk=traffic.risk,
                assumptions=common_assumptions,
            ),
        )
        preferred = (
            StrategyAction.PIT_NEXT_LAP
            if pit_next < stay_then_pit
            else StrategyAction.STAY_OUT_ONE_LAP
        )
        confidence = min(0.9, 0.35 + trend.sample_count * 0.07)
        if traffic.risk is TrafficRisk.UNKNOWN:
            confidence = max(0.1, confidence - 0.2)
        evidence = (
            f"{trend.sample_count} valid current-stint pace samples.",
            f"Estimated current pace: {trend.pace_ms / 1000:.3f}s.",
            f"Estimated degradation: {degradation:.1f}ms/lap.",
            f"Predicted rejoin: P{traffic.predicted_rejoin_position or '?'} "
            f"with {traffic.risk} traffic risk.",
        )
        return StrategyAssessment(
            session_id=snapshot.session_id,
            cutoff_lap=snapshot.cutoff_lap,
            driver_id=driver_id,
            preferred_action=preferred,
            confidence=round(confidence, 2),
            options=options,
            evidence=evidence,
            warnings=tuple(warnings),
            max_source_lap=max(trend.max_source_lap, traffic.max_source_lap),
        )

"""Cutoff-safe builders separating evidence selection from simulation."""

from statistics import median

from f1_pitwall.analytics import TyreAnalyzer
from f1_pitwall.analytics.pits import calculate_pit_loss
from f1_pitwall.domain import Compound, DriverStatus, RaceDataset
from f1_pitwall.replay import ReplayBuilder
from f1_pitwall.simulation.models import Entrant, PreRaceRequest, RaceRules, SimulationState


def build_pre_race(request: PreRaceRequest) -> SimulationState:
    """Reject future observations, then combine per-driver/team available pace evidence."""
    if request.as_of >= request.race_start:
        raise ValueError("pre-race as_of must precede race_start")
    if any(
        item.available_at > request.as_of or item.observed_at > request.as_of
        for item in request.evidence
    ):
        raise ValueError("future evidence cannot enter a pre-race state")
    entrants = []
    weights = {"practice": 4, "historical": 2, "driver": 2, "team": 1}
    for entrant in request.entrants:
        evidence = [
            item
            for item in request.evidence
            if item.driver_id == entrant.driver_id
            or (item.driver_id is None and item.team_id == entrant.team_id)
        ]
        updates: dict[str, object] = {}
        if evidence:
            total = sum(weights[item.source] for item in evidence)
            updates["base_pace_ms"] = (
                sum(item.pace_ms * weights[item.source] for item in evidence) / total
            )
            updates["confidence"] = min(0.85, 0.35 + 0.08 * len(evidence))
            degradation = [
                item.degradation_ms_per_lap
                for item in evidence
                if item.degradation_ms_per_lap is not None
            ]
            if degradation:
                spec = next(
                    t for t in request.rules.tyres if t.compound == entrant.current_compound
                )
                updates["degradation_multiplier"] = max(
                    0.1, min(5, median(degradation) / max(1, spec.degradation_ms_per_lap))
                )
        entrants.append(entrant.model_copy(update=updates))
    return SimulationState(
        event_id=request.event_id,
        total_laps=request.total_laps,
        entrants=tuple(entrants),
        rules=request.rules,
        as_of=request.as_of,
        race_start=request.race_start,
        warnings=(
            f"Grid source: {request.grid_source}; verify penalties and pit-lane starts.",
            "Entrant pace defaults are assumptions wherever timed evidence is missing.",
        ),
    )


def build_replay_state(
    dataset: RaceDataset, lap: int, rules: RaceRules | None = None
) -> SimulationState:
    """Build solely from completed-lap observations at or before the requested lap."""
    snapshot = ReplayBuilder(dataset).build(lap)
    resolved = rules or RaceRules()
    if rules is None:
        pit_loss = calculate_pit_loss(dataset, lap)
        if pit_loss.sample_count:
            resolved = resolved.model_copy(
                update={
                    "pit_loss_ms": pit_loss.pit_loss_ms,
                    "out_lap_penalty_ms": 0,
                    "assumptions": (*resolved.assumptions, pit_loss.assumption),
                }
            )
    specs = {tyre.compound: tyre for tyre in resolved.tyres}
    visible = [record for record in dataset.laps if record.lap_number <= lap]
    observed_wet = any(
        record.compound in {Compound.WET, Compound.INTERMEDIATE} for record in visible
    )
    if observed_wet and rules is None:
        from f1_pitwall.simulation.models import TyreSpec

        resolved = resolved.model_copy(
            update={
                "tyres": (
                    *resolved.tyres,
                    TyreSpec(
                        compound=Compound.INTERMEDIATE, degradation_ms_per_lap=60, max_life_laps=35
                    ),
                    TyreSpec(compound=Compound.WET, degradation_ms_per_lap=45, max_life_laps=40),
                )
            }
        )
        specs = {tyre.compound: tyre for tyre in resolved.tyres}
    tyre_analyzer = TyreAnalyzer(dataset)
    field_pace = median(
        [
            driver.rolling_pace_ms
            for driver in snapshot.drivers
            if driver.rolling_pace_ms is not None
        ]
        or [90000]
    )
    entrants = []
    excluded = []
    warnings = [warning.message for warning in snapshot.warnings]
    for driver in snapshot.drivers:
        if driver.status in {DriverStatus.RETIRED, DriverStatus.DNS, DriverStatus.DSQ}:
            excluded.append(driver.driver_id)
            continue
        info = dataset.drivers[driver.driver_id]
        compound = driver.compound if driver.compound in specs else resolved.tyres[0].compound
        spec = specs[compound]
        trend = tyre_analyzer.estimate(driver.driver_id, lap) if driver.completed_laps else None
        age = driver.tyre_age_laps or 0
        slope = (
            max(0, trend.degradation_ms_per_lap)
            if trend and trend.degradation_ms_per_lap is not None
            else spec.degradation_ms_per_lap
        )
        pace = driver.rolling_pace_ms or field_pace
        used = tuple(
            sorted(
                {
                    record.compound
                    for record in visible
                    if record.driver_id == driver.driver_id and record.compound != Compound.UNKNOWN
                }
            )
        )
        if driver.compound == Compound.UNKNOWN or not driver.rolling_pace_ms:
            warnings.append(f"{driver.driver_id}: missing pace/tyre data; using field assumptions.")
        # Missing timing is uncertainty, not a fabricated retirement. Lap deficits are explicit.
        gap: float | None = driver.gap_to_leader_ms
        if gap is None:
            gap = (
                driver.laps_behind * field_pace + (driver.position or len(snapshot.drivers)) * 1000
            )
        entrants.append(
            Entrant(
                driver_id=driver.driver_id,
                team_id=info.team_id or info.team_name,
                grid_position=driver.position or info.grid_position or len(snapshot.drivers),
                base_pace_ms=max(1000, pace - slope * age - spec.pace_offset_ms),
                initial_gap_ms=gap,
                current_compound=compound,
                tyre_age_laps=age,
                used_compounds=used,
                stops_completed=driver.pit_stop_count,
                available_compounds=(compound,)
                if compound not in {Compound.SOFT, Compound.MEDIUM, Compound.HARD}
                else tuple(
                    c for c in specs if c in {Compound.SOFT, Compound.MEDIUM, Compound.HARD}
                ),
                degradation_multiplier=max(
                    0.1, min(5, slope / max(1, spec.degradation_ms_per_lap))
                ),
                confidence=(trend.confidence if trend else 0.1),
            )
        )
    return SimulationState(
        event_id=dataset.metadata.session_id,
        total_laps=dataset.metadata.total_laps,
        cutoff_lap=lap,
        entrants=tuple(entrants),
        rules=resolved,
        excluded_driver_ids=tuple(excluded),
        warnings=tuple(warnings),
    )

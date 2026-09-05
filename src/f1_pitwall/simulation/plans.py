"""Finite, tyre-constrained full-distance strategy candidates."""

from itertools import product

from f1_pitwall.simulation.models import DRY, Entrant, PitStop, SimulationState, StrategyPlan


def candidate_strategies(state: SimulationState, entrant: Entrant) -> tuple[StrategyPlan, ...]:
    """Enumerate bounded stop schedules, including legal no-stop finishes."""
    specs = {tyre.compound: tyre for tyre in state.rules.tyres}
    available = entrant.available_compounds or tuple(specs)
    remaining = state.total_laps - state.cutoff_lap
    starts = available if state.cutoff_lap == 0 else (entrant.current_compound,)
    candidates: dict[tuple[object, ...], StrategyPlan] = {}
    for count in range(state.rules.max_stops + 1):
        if (
            count + entrant.stops_completed < state.rules.minimum_stops
            or count > remaining
            or (count == remaining and state.cutoff_lap == 0)
        ):
            continue
        for start in starts:
            for following in product(available, repeat=count):
                compounds = (start, *following)
                used = set(entrant.used_compounds) | set(compounds)
                wet_used = bool(used - DRY)
                if (
                    state.rules.require_two_dry_compounds
                    and not wet_used
                    and (
                        len(used & DRY) < 2
                        or (
                            state.rules.mandatory_race_compounds
                            and not used.intersection(state.rules.mandatory_race_compounds)
                        )
                    )
                ):
                    continue
                new_sets = compounds if state.cutoff_lap == 0 else following
                if entrant.compound_sets and any(
                    new_sets.count(c) > entrant.compound_sets.get(c, 0) for c in set(new_sets)
                ):
                    continue
                capacities = [specs[c].max_life_laps for c in compounds]
                capacities[0] = max(
                    0, capacities[0] - (entrant.tyre_age_laps if state.cutoff_lap else 0)
                )
                if sum(capacities) < remaining:
                    continue
                for shift in (-remaining, -4, -2, 0, 2, 4):
                    lengths: list[int] = []
                    todo = remaining
                    for index, capacity in enumerate(capacities):
                        slots = len(capacities) - index
                        duration = todo if slots == 1 else round(todo / slots)
                        if index == 0 and slots > 1:
                            duration += shift
                        duration = max(
                            0 if index == 0 and state.cutoff_lap and count else 1,
                            todo - sum(capacities[index + 1 :]),
                            min(capacity, duration, todo - (slots - 1)),
                        )
                        lengths.append(duration)
                        todo -= duration
                    if todo or any(
                        length > cap for length, cap in zip(lengths, capacities, strict=True)
                    ):
                        continue
                    elapsed = 0.0
                    traffic = 0.0
                    stops = []
                    lap = state.cutoff_lap
                    for index, (compound, length) in enumerate(
                        zip(compounds, lengths, strict=True)
                    ):
                        spec = specs[compound]
                        age = entrant.tyre_age_laps if index == 0 and state.cutoff_lap else 0
                        elapsed += length * (entrant.base_pace_ms + spec.pace_offset_ms)
                        elapsed += (
                            spec.degradation_ms_per_lap
                            * entrant.degradation_multiplier
                            * (length * age + length * (length + 1) / 2)
                        )
                        lap += length
                        if index < count:
                            stops.append(PitStop(after_lap=lap, compound=compounds[index + 1]))
                            elapsed += state.rules.pit_loss_ms + state.rules.out_lap_penalty_ms
                            rejoin_gap = entrant.initial_gap_ms + state.rules.pit_loss_ms
                            for rival in state.entrants:
                                if rival.driver_id == entrant.driver_id:
                                    continue
                                rival_gap = rival.initial_gap_ms + (
                                    rival.base_pace_ms - entrant.base_pace_ms
                                ) * (lap - state.cutoff_lap)
                                if 0 <= rejoin_gap - rival_gap <= 3000:
                                    traffic += state.rules.traffic_headway_ms * min(3, remaining)
                    key = (start, *((stop.after_lap, stop.compound) for stop in stops))
                    label = (
                        start.value
                        + " "
                        + (
                            ", ".join(f"L{stop.after_lap}→{stop.compound}" for stop in stops)
                            or "to finish"
                        )
                    )
                    candidates[key] = StrategyPlan(
                        name=label,
                        starting_compound=start,
                        stops=tuple(stops),
                        projected_time_ms=round(elapsed + traffic, 2),
                        traffic_penalty_ms=traffic,
                    )
    return tuple(
        sorted(candidates.values(), key=lambda plan: (plan.projected_time_ms, plan.name))[:16]
    )

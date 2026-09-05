"""Seeded Monte Carlo races and position-dependent strategy utility."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from f1_pitwall.simulation.models import (
    DriverPrediction,
    SimulationResult,
    SimulationState,
    StrategyPlan,
)
from f1_pitwall.simulation.plans import candidate_strategies


def _race(
    state: SimulationState, plans: list[StrategyPlan], samples: int, seed: int
) -> NDArray[np.int64]:
    """Vectorize trials, retaining lap-wise traffic/overtaking interactions."""
    rng = np.random.default_rng(seed)
    size = len(state.entrants)
    remaining = state.total_laps - state.cutoff_lap
    specs = {tyre.compound: tyre for tyre in state.rules.tyres}
    times = np.tile(
        [
            entrant.initial_gap_ms + ((entrant.grid_position or size) - 1) * 180
            if state.cutoff_lap == 0
            else entrant.initial_gap_ms
            for entrant in state.entrants
        ],
        (samples, 1),
    )
    sigma = np.array([entrant.pace_sigma_ms for entrant in state.entrants])
    weekend_noise = rng.normal(0, sigma * 0.65, (samples, size))
    rows = np.arange(samples)
    compounds = [plan.starting_compound for plan in plans]
    ages = [entrant.tyre_age_laps if state.cutoff_lap else 0 for entrant in state.entrants]
    for lap in range(state.cutoff_lap + 1, state.cutoff_lap + remaining + 1):
        old_order = np.argsort(times, axis=1, kind="stable")
        pace = np.zeros(size)
        pitting = np.zeros(size, dtype=bool)
        for index, (entrant, plan) in enumerate(zip(state.entrants, plans, strict=True)):
            stop = next((stop for stop in plan.stops if stop.after_lap == lap - 1), None)
            if stop:
                compounds[index] = stop.compound
                ages[index] = 0
                pitting[index] = True
                pace[index] += state.rules.pit_loss_ms + state.rules.out_lap_penalty_ms
            ages[index] += 1
            tyre = specs[compounds[index]]
            pace[index] += (
                entrant.base_pace_ms
                + tyre.pace_offset_ms
                + (tyre.degradation_ms_per_lap * entrant.degradation_multiplier * ages[index])
            )
        lap_times = pace + weekend_noise + rng.normal(0, sigma, (samples, size))
        updated = times + np.maximum(1000, lap_times)
        for place in range(1, size):
            behind = old_order[:, place]
            ahead = old_order[:, place - 1]
            close = times[rows, behind] - times[rows, ahead] < 2000
            blocked = (
                close
                & ~pitting[behind]
                & ~pitting[ahead]
                & (
                    lap_times[rows, ahead] - lap_times[rows, behind]
                    < state.rules.overtaking_delta_ms
                )
            )
            updated[rows, behind] = np.where(
                blocked,
                np.maximum(
                    updated[rows, behind], updated[rows, ahead] + state.rules.traffic_headway_ms
                ),
                updated[rows, behind],
            )
        times = updated
    order = np.argsort(times, axis=1, kind="stable")
    return np.argsort(order, axis=1, kind="stable").astype(np.int64) + 1


def _utility(
    finishes: NDArray[np.int64], grid: int, size: int, points_schedule: tuple[float, ...]
) -> float:
    points = np.array([0, *points_schedule, *([0] * size)])[finishes]
    strength = 1 - (max(1, grid) - 1) / max(1, size - 1)
    gain = grid - float(np.mean(finishes))
    # Smooth weights: leaders protect wins; midfield values points; rear values gain/upside.
    value = (
        (0.4 + strength) * float(np.mean(points))
        + (1.4 - strength) * gain
        + 12 * strength**4 * float(np.mean(finishes == 1))
        + 4 * (1 - strength) * float(np.mean(points > 0))
        - (0.25 + strength) * max(0, float(np.quantile(finishes, 0.95)) - grid)
    )
    return value


def simulate_race(
    state: SimulationState, simulations: int = 100, seed: int = 42
) -> SimulationResult:
    """Compare each driver's two best legal candidates against common rival plans/noise."""
    if not 1 <= simulations <= 5000 or not 0 <= seed <= 2**32 - 1:
        raise ValueError("simulations must be 1..5000 and seed an unsigned 32-bit integer")
    candidates = [candidate_strategies(state, entrant) for entrant in state.entrants]
    infeasible = [
        entrant.driver_id
        for entrant, plans in zip(state.entrants, candidates, strict=True)
        if not plans
    ]
    if infeasible:
        raise ValueError(
            "No legal tyre-life strategy for: "
            + ", ".join(infeasible)
            + "; review event tyre models, allocations and stop limits"
        )
    baseline = [plans[0] for plans in candidates]
    baseline_finishes = _race(state, baseline, simulations, seed)
    predictions = []
    size = len(state.entrants)
    for index, entrant in enumerate(state.entrants):
        finishes = baseline_finishes[:, index]
        best = baseline[index]
        alternative = candidates[index][1] if len(candidates[index]) > 1 else None
        grid = entrant.grid_position or size
        utility = _utility(finishes, grid, size, state.rules.points)
        if alternative:
            changed = baseline.copy()
            changed[index] = alternative
            other_finishes = _race(state, changed, simulations, seed)[:, index]
            other_utility = _utility(other_finishes, grid, size, state.rules.points)
            if other_utility > utility:
                best, alternative = alternative, best
                finishes, utility = other_finishes, other_utility
        counts = np.bincount(finishes, minlength=size + 1)
        points = np.array([0, *state.rules.points, *([0] * size)])[finishes]
        upside = int(np.quantile(finishes, 0.05, method="higher"))
        downside = int(np.quantile(finishes, 0.95, method="higher"))
        competitive_stops = [
            plan.stops[0].after_lap
            for plan in candidates[index]
            if plan.stops and plan.projected_time_ms <= best.projected_time_ms + 2000
        ]
        predictions.append(
            DriverPrediction(
                driver_id=entrant.driver_id,
                expected_finish=round(float(np.mean(finishes)), 3),
                median_finish=float(np.median(finishes)),
                expected_positions_gained=round(grid - float(np.mean(finishes)), 3),
                expected_points=round(float(np.mean(points)), 3),
                points_probability=float(np.mean(points > 0)),
                top10_probability=float(np.mean(finishes <= 10)),
                podium_probability=float(np.mean(finishes <= 3)),
                win_probability=float(np.mean(finishes == 1)),
                realistic_best_result=upside,
                realistic_downside=downside,
                finish_distribution={
                    place: int(counts[place]) / simulations for place in range(1, size + 1)
                },
                recommended_strategy=best,
                alternative_strategy=alternative,
                most_successful_strategy=best.name,
                pit_window_start_lap=min(competitive_stops) if competitive_stops else None,
                pit_window_end_lap=max(competitive_stops) if competitive_stops else None,
                main_opportunity=f"Upside P{upside}; use stop timing to challenge nearby rivals.",
                main_threat=f"Downside P{downside}; traffic and pace uncertainty can erase gains.",
                confidence=round(entrant.confidence * min(1, (simulations / 500) ** 0.5), 3),
                utility=round(utility, 3),
            )
        )
    return SimulationResult(
        event_id=state.event_id,
        simulations=simulations,
        seed=seed,
        cutoff_lap=state.cutoff_lap,
        predictions=tuple(predictions),
        excluded_driver_ids=state.excluded_driver_ids,
        warnings=state.warnings + state.rules.assumptions,
    )

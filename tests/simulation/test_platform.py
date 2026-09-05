from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from f1_pitwall.analytics import TyreAnalyzer
from f1_pitwall.analytics.pits import calculate_overcut, calculate_pit_loss, calculate_undercut
from f1_pitwall.application import PitWallService
from f1_pitwall.domain import Compound, DriverStatus
from f1_pitwall.evaluations.historical import evaluate_historical
from f1_pitwall.ingestion import create_demo_dataset
from f1_pitwall.simulation.models import (
    Entrant,
    PaceEvidence,
    PreRaceRequest,
    RaceRules,
    SimulationState,
    TyreSpec,
)
from f1_pitwall.simulation.plans import candidate_strategies
from f1_pitwall.simulation.race import simulate_race
from f1_pitwall.simulation.state import build_pre_race, build_replay_state


def pre_race(size: int = 12) -> PreRaceRequest:
    now = datetime(2026, 9, 5, tzinfo=UTC)
    return PreRaceRequest(
        event_id="synthetic-next",
        race_start=now + timedelta(days=1),
        as_of=now,
        total_laps=30,
        entrants=tuple(
            Entrant(
                driver_id=f"driver-{i}",
                team_id=f"team-{i // 2}",
                grid_position=i + 1,
                base_pace_ms=90000 + i * 100,
            )
            for i in range(size)
        ),
    )


@pytest.mark.parametrize("size", [1, 19, 22, 26])
def test_complete_grid_including_entrants_without_laps(size: int) -> None:
    dataset = create_demo_dataset(size)
    dataset = dataset.model_copy(
        update={"laps": tuple(lap for lap in dataset.laps if lap.driver_id != "D001")}
    )
    snapshot = PitWallService(dataset).snapshot(12)
    assert len(snapshot.drivers) == size
    missing = next(driver for driver in snapshot.drivers if driver.driver_id == "D001")
    assert missing.status == DriverStatus.UNKNOWN
    assert missing.completed_laps == 0


def test_future_mutation_cannot_change_replay_analysis_or_predictions() -> None:
    dataset = create_demo_dataset(12)
    changed = dataset.model_copy(
        update={
            "laps": tuple(
                lap.model_copy(
                    update={
                        "lap_time_ms": 1,
                        "compound": Compound.WET,
                        "observed_status": DriverStatus.RETIRED,
                    }
                )
                if lap.lap_number > 12
                else lap
                for lap in dataset.laps
            )
        }
    )
    assert PitWallService(dataset).snapshot(12) == PitWallService(changed).snapshot(12)
    assert TyreAnalyzer(dataset).estimate("D001", 12) == TyreAnalyzer(changed).estimate("D001", 12)
    assert calculate_pit_loss(dataset, 12) == calculate_pit_loss(changed, 12)
    state = build_replay_state(dataset, 12)
    assert state == build_replay_state(changed, 12)
    assert simulate_race(state, 10, 7) == simulate_race(build_replay_state(changed, 12), 10, 7)


def test_seeded_full_grid_predictions_include_backmarkers() -> None:
    state = build_pre_race(pre_race(22))
    result = simulate_race(state, 20, 8)
    assert result == simulate_race(state, 20, 8)
    assert result != simulate_race(state, 20, 9)
    assert len(result.predictions) == 22
    for prediction in result.predictions:
        assert sum(prediction.finish_distribution.values()) == pytest.approx(1)
        assert 1 <= prediction.realistic_best_result <= prediction.realistic_downside <= 22
        assert prediction.recommended_strategy
        assert prediction.alternative_strategy
        assert prediction.main_opportunity
        assert prediction.main_threat
    assert result.predictions[-1].win_probability < result.predictions[0].win_probability


def test_plans_respect_compounds_life_allocations_and_stops() -> None:
    state = build_pre_race(pre_race())
    entrant = state.entrants[0].model_copy(
        update={
            "available_compounds": (Compound.MEDIUM, Compound.HARD),
            "compound_sets": {Compound.MEDIUM: 1, Compound.HARD: 1},
        }
    )
    plans = candidate_strategies(state, entrant)
    assert plans
    for plan in plans:
        assert len(plan.stops) == 1
        assert plan.starting_compound != plan.stops[0].compound
        assert 0 < plan.stops[0].after_lap < state.total_laps
    impossible = state.model_copy(update={"rules": RaceRules(max_stops=0)})
    assert not candidate_strategies(impossible, entrant)
    with pytest.raises(ValueError, match="No legal"):
        simulate_race(impossible, 2)


def test_legal_stay_out_finish_and_wet_race() -> None:
    state = build_replay_state(create_demo_dataset(3), 29)
    entrant = state.entrants[0]
    assert candidate_strategies(state, entrant)[0].stops == ()
    rules = RaceRules(
        tyres=(TyreSpec(compound=Compound.WET, degradation_ms_per_lap=40, max_life_laps=40),)
    )
    request = pre_race(2).model_copy(
        update={
            "rules": rules,
            "entrants": tuple(
                entrant.model_copy(update={"current_compound": Compound.WET})
                for entrant in pre_race(2).entrants
            ),
        }
    )
    assert simulate_race(build_pre_race(request), 3).predictions[0].recommended_strategy.stops == ()


def test_pre_race_rejects_future_information_and_uses_available_evidence() -> None:
    request = pre_race()
    evidence = PaceEvidence(
        driver_id="driver-0",
        available_at=request.as_of,
        observed_at=request.as_of,
        source="practice",
        pace_ms=89000,
        degradation_ms_per_lap=80,
    )
    state = build_pre_race(request.model_copy(update={"evidence": (evidence,)}))
    assert state.entrants[0].base_pace_ms == 89000
    assert state.entrants[0].confidence > request.entrants[0].confidence
    for key in ("available_at", "observed_at"):
        with pytest.raises(ValueError, match="future evidence"):
            build_pre_race(
                request.model_copy(
                    update={"evidence": (evidence.model_copy(update={key: request.race_start}),)}
                )
            )
    with pytest.raises(ValueError, match="precede"):
        build_pre_race(request.model_copy(update={"as_of": request.race_start}))


def test_missing_data_reduces_confidence_and_observed_retirement_is_excluded() -> None:
    dataset = create_demo_dataset(3)
    dataset = dataset.model_copy(
        update={
            "laps": tuple(
                lap.model_copy(update={"observed_status": DriverStatus.RETIRED})
                if lap.driver_id == "D001" and lap.lap_number == 12
                else lap.model_copy(update={"lap_time_ms": None, "compound": Compound.UNKNOWN})
                if lap.driver_id == "D002"
                else lap
                for lap in dataset.laps
            )
        }
    )
    state = build_replay_state(dataset, 12)
    assert state.excluded_driver_ids == ("D001",)
    assert len(simulate_race(state, 3).predictions) == 2
    assert state.warnings


def test_pit_models_use_visible_stops_and_compare_equal_horizons() -> None:
    dataset = create_demo_dataset(5)
    assert calculate_pit_loss(dataset, 12).sample_count == 0
    estimate = calculate_pit_loss(dataset, 18)
    assert estimate.sample_count == 5
    assert 20000 < estimate.pit_loss_ms < 30000
    undercut = calculate_undercut(93000, 90000, 2)
    assert undercut.undercut_gain_ms == 4200
    assert calculate_overcut(93000, 90000, 2).overcut_gain_ms == -4200
    with pytest.raises(ValueError, match="invalid"):
        calculate_pit_loss(dataset, 0)
    with pytest.raises(ValueError, match="invalid"):
        calculate_undercut(0, 90000)


def test_anomalies_sc_and_pit_laps_do_not_drive_tyre_fit() -> None:
    dataset = create_demo_dataset(3)
    changed = dataset.model_copy(
        update={
            "laps": tuple(
                lap.model_copy(update={"lap_time_ms": 400000})
                if lap.driver_id == "D001" and lap.lap_number == 8
                else lap
                for lap in dataset.laps
            )
        }
    )
    trend = TyreAnalyzer(changed).estimate("D001", 12)
    assert trend.sample_count == 7
    assert trend.pace_ms
    assert trend.pace_ms < 100000


def test_historical_evaluation_has_provenance_and_holdout_metrics() -> None:
    result = evaluate_historical(create_demo_dataset(5), 12, 3)
    assert result.full_grid_correct
    assert result.evaluated_drivers == 5
    assert result.finishing_position_mae is not None
    assert result.pit_window_mae_laps is not None
    assert result.model_version
    assert result.simulator_version


@pytest.mark.parametrize(
    "change",
    [{"cutoff_lap": 30}, {"entrants": ()}, {"race_start": datetime(2026, 9, 6, tzinfo=UTC)}],
)
def test_invalid_simulation_state_rejected(change: dict[str, object]) -> None:
    state = build_pre_race(pre_race()).model_dump()
    state.update(change)
    if "race_start" in change:
        state["as_of"] = None
    with pytest.raises(ValidationError):
        SimulationState.model_validate(state)


@pytest.mark.parametrize(("samples", "seed"), [(0, 42), (5001, 42), (1, -1)])
def test_invalid_simulation_budget_rejected(samples: int, seed: int) -> None:
    with pytest.raises(ValueError, match="simulations"):
        simulate_race(build_pre_race(pre_race(1)), samples, seed)


def test_exhausted_tyres_can_be_changed_immediately() -> None:
    state = build_replay_state(create_demo_dataset(3), 12)
    entrant = state.entrants[0].model_copy(update={"tyre_age_laps": 99})
    plans = candidate_strategies(state, entrant)
    assert plans
    assert all(plan.stops[0].after_lap == state.cutoff_lap for plan in plans)


def test_final_lap_can_meet_outstanding_compound_rule() -> None:
    state = build_replay_state(create_demo_dataset(3), 29)
    entrant = state.entrants[0].model_copy(
        update={"current_compound": Compound.MEDIUM, "used_compounds": (Compound.MEDIUM,)}
    )
    plans = candidate_strategies(state, entrant)
    assert plans
    assert plans[0].stops[0].after_lap == 29


def test_replay_uses_observed_pit_loss_when_clean_stops_exist() -> None:
    state = build_replay_state(create_demo_dataset(5), 18)
    assert state.rules.pit_loss_ms != 24000
    assert state.rules.out_lap_penalty_ms == 0


def test_wet_observations_missing_laps_and_holdout_without_results() -> None:
    dataset = create_demo_dataset(4)
    dataset = dataset.model_copy(
        update={
            "laps": tuple(
                lap.model_copy(update={"compound": Compound.WET})
                for lap in dataset.laps
                if lap.driver_id != "D004" and lap.lap_number <= 12
            )
        }
    )
    state = build_replay_state(dataset, 12)
    assert state.entrants[-1].confidence == 0.1
    assert simulate_race(state, 2).predictions
    report = evaluate_historical(dataset, 12, 2)
    assert report.finishing_position_mae is None
    assert report.pit_window_mae_laps is None


def test_large_simulation_budget_with_small_field() -> None:
    state = build_pre_race(pre_race(2))
    assert simulate_race(state, 5000, 9).simulations == 5000


def test_status_observations_are_cutoff_safe_and_do_not_invent_completed_laps() -> None:
    from f1_pitwall.domain.models import StatusRecord

    dataset = create_demo_dataset(4)
    dataset = dataset.model_copy(
        update={
            "laps": tuple(lap for lap in dataset.laps if lap.driver_id != "D004"),
            "statuses": (
                StatusRecord(driver_id="D004", source_lap=0, status=DriverStatus.DNS),
                StatusRecord(driver_id="D001", source_lap=20, status=DriverStatus.DSQ),
            ),
        }
    )
    early = PitWallService(dataset).snapshot(12)
    dns = next(driver for driver in early.drivers if driver.driver_id == "D004")
    assert dns.status == DriverStatus.DNS
    assert dns.completed_laps == 0
    assert early.drivers[0].status != DriverStatus.DSQ
    assert "D004" in build_replay_state(dataset, 12).excluded_driver_ids
    assert "D001" in build_replay_state(dataset, 21).excluded_driver_ids

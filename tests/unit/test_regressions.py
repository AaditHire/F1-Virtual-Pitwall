import pytest

from f1_pitwall.analytics import TrafficAnalyzer, TyreAnalyzer
from f1_pitwall.application import PitWallService
from f1_pitwall.domain import DriverStatus, StrategyAction, TrafficRisk
from f1_pitwall.radio import RadioCategory, classify_radio
from f1_pitwall.simulation import StrategyAdvisor


def test_strategy_counts_every_projected_lap(service: PitWallService) -> None:
    dataset = service.dataset.model_copy(
        update={
            "laps": tuple(
                lap.model_copy(update={"lap_time_ms": 90_000}) for lap in service.dataset.laps
            ),
        }
    )
    assessment = StrategyAdvisor(dataset).assess(service.snapshot(12), "NOR")
    # Five complete laps plus one pit loss and one out-lap penalty.
    assert assessment.options[0].projected_time_ms == 5 * 90_000 + 24_000 + 5_000


@pytest.mark.parametrize("lap", [28, 29, 30])
def test_strategy_does_not_project_beyond_the_finish(service: PitWallService, lap: int) -> None:
    assessment = service.strategy(lap, "NOR")
    assert assessment.preferred_action == StrategyAction.NO_RECOMMENDATION
    assert not assessment.options


def test_strategy_shortens_horizon_to_remaining_laps(service: PitWallService) -> None:
    assessment = service.strategy(26, "NOR")
    assert "Projection horizon is 4 laps." in assessment.options[0].assumptions


def test_tyre_fit_is_independent_of_input_order(service: PitWallService) -> None:
    reversed_dataset = service.dataset.model_copy(update={"laps": service.dataset.laps[::-1]})
    assert TyreAnalyzer(reversed_dataset).estimate("NOR", 18) == service.tyre_trend(18, "NOR")


def test_missing_timing_does_not_establish_retirement(service: PitWallService) -> None:
    dataset = service.dataset.model_copy(
        update={
            "laps": tuple(
                lap for lap in service.dataset.laps if lap.driver_id != "NOR" or lap.lap_number <= 8
            ),
        }
    )
    snapshot = PitWallService(dataset).snapshot(12)
    driver = next(driver for driver in snapshot.drivers if driver.driver_id == "NOR")
    assert driver.status == DriverStatus.UNKNOWN
    assert any(warning.code == "STALE_TIMING" for warning in snapshot.warnings)
    assert TrafficAnalyzer().analyze(snapshot, "RUS").risk == TrafficRisk.UNKNOWN


@pytest.mark.parametrize("text", ["We have graining", "Check the gearbox", "Interval is stable"])
def test_radio_does_not_match_keywords_inside_words(text: str) -> None:
    signal = classify_radio(text)
    assert RadioCategory.WEATHER not in signal.categories
    assert RadioCategory.STRATEGY not in signal.categories


def test_radio_recognizes_plural_tyres_and_variable_spacing() -> None:
    signal = classify_radio("Tyres are gone, stay   out")
    assert RadioCategory.TYRES in signal.categories
    assert RadioCategory.STRATEGY in signal.categories


def test_lap_chart_quality_uses_flags_not_circuit_speed(service: PitWallService) -> None:
    dataset = service.dataset.model_copy(
        update={
            "laps": tuple(
                lap.model_copy(update={"lap_time_ms": 125_000}) for lap in service.dataset.laps
            ),
        }
    )
    laps = PitWallService(dataset).lap_times(13, {" nor "})
    assert any(lap["is_clean"] for lap in laps)
    assert not next(lap for lap in laps if lap["lap_number"] == 13)["is_clean"]


def test_lap_chart_rejects_unknown_driver(service: PitWallService) -> None:
    with pytest.raises(ValueError, match="unknown drivers"):
        service.lap_times(12, {"XYZ"})


def test_analytics_reject_invalid_parameters(service: PitWallService) -> None:
    with pytest.raises(ValueError, match="window"):
        TyreAnalyzer(service.dataset).estimate("NOR", 12, window=0)
    with pytest.raises(ValueError, match="cutoff"):
        TyreAnalyzer(service.dataset).estimate("NOR", 99)
    with pytest.raises(ValueError, match="pit loss"):
        TrafficAnalyzer().analyze(service.snapshot(12), "NOR", pit_loss_ms=-1)
    with pytest.raises(ValueError, match="pit loss"):
        StrategyAdvisor(service.dataset).assess(service.snapshot(12), "NOR", pit_loss_ms=-1)

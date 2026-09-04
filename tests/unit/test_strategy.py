import pytest

from f1_pitwall.application import PitWallService
from f1_pitwall.domain import StrategyAction


def test_strategy_is_auditable(service: PitWallService) -> None:
    assessment = service.strategy(12, "nor")
    assert assessment.driver_id == "NOR"
    assert assessment.preferred_action in {
        StrategyAction.PIT_NEXT_LAP,
        StrategyAction.STAY_OUT_ONE_LAP,
    }
    assert len(assessment.options) == 2
    assert assessment.max_source_lap <= 12
    assert assessment.evidence


def test_strategy_requires_valid_horizon(service: PitWallService) -> None:
    with pytest.raises(ValueError, match="at least 3"):
        service._strategy.assess(service.snapshot(12), "NOR", horizon_laps=2)

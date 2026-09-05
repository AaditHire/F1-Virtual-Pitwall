import pytest

from f1_pitwall.analytics import TrafficAnalyzer, TyreAnalyzer
from f1_pitwall.application import PitWallService
from f1_pitwall.domain import TrafficRisk


def test_tyre_analyzer_uses_current_stint(service: PitWallService) -> None:
    trend = TyreAnalyzer(service.dataset).estimate("D001", 12)
    assert trend.sample_count == 8
    assert trend.pace_ms is not None
    assert trend.degradation_ms_per_lap is not None
    assert trend.max_source_lap == 12


def test_tyre_analyzer_requires_visible_driver(service: PitWallService) -> None:
    with pytest.raises(ValueError, match="no visible laps"):
        TyreAnalyzer(service.dataset).estimate("XXX", 12)


def test_traffic_analyzer_predicts_rejoin(service: PitWallService) -> None:
    traffic = TrafficAnalyzer().analyze(service.snapshot(12), "D001")
    assert traffic.predicted_rejoin_position is not None
    assert traffic.risk in {TrafficRisk.LOW, TrafficRisk.MEDIUM, TrafficRisk.HIGH}
    assert traffic.max_source_lap == 12


def test_traffic_analyzer_rejects_missing_driver(service: PitWallService) -> None:
    with pytest.raises(ValueError, match="not present"):
        TrafficAnalyzer().analyze(service.snapshot(12), "XXX")


def test_service_analysis_facade_validates_cutoffs(service: PitWallService) -> None:
    assert service.tyre_trend(12, "d001").max_source_lap <= 12
    assert service.traffic(12, "d001").max_source_lap <= 12
    with pytest.raises(ValueError, match="between 1 and"):
        service.lap_times(99)
    with pytest.raises(ValueError, match="between 1 and"):
        service.tyre_trend(0, "D001")

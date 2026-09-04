from f1_pitwall.application import PitWallService
from f1_pitwall.evaluations import run_evaluations


def test_baseline_evaluations_pass(service: PitWallService) -> None:
    results = run_evaluations(service)
    assert len(results) == 3
    assert all(result.passed for result in results)

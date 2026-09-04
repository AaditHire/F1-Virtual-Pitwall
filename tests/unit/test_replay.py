import pytest

from f1_pitwall.application import PitWallService


def test_snapshot_is_deterministic_and_cutoff_safe(service: PitWallService) -> None:
    first = service.snapshot(12)
    second = service.snapshot(12)
    assert first.snapshot_hash == second.snapshot_hash
    assert max(driver.max_source_lap for driver in first.drivers) == 12
    assert all(driver.pit_stop_count == 0 for driver in first.drivers)


def test_snapshot_tracks_pit_stops(service: PitWallService) -> None:
    snapshot = service.snapshot(16)
    assert all(driver.pit_stop_count == 1 for driver in snapshot.drivers)


@pytest.mark.parametrize("lap", [0, 31])
def test_snapshot_rejects_invalid_cutoff(service: PitWallService, lap: int) -> None:
    with pytest.raises(ValueError, match="cutoff_lap"):
        service.snapshot(lap)

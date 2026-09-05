import pytest
from pydantic import ValidationError

from f1_pitwall.domain import LapRecord, RaceDataset
from f1_pitwall.ingestion import create_demo_dataset


def test_lap_record_rejects_future_source() -> None:
    with pytest.raises(ValidationError, match="source_lap must equal"):
        LapRecord(driver_id="D001", lap_number=3, source_lap=4)


def test_dataset_rejects_unknown_driver() -> None:
    dataset = create_demo_dataset()
    bad_lap = dataset.laps[0].model_copy(update={"driver_id": "XXX"})
    with pytest.raises(ValidationError, match="unknown driver"):
        RaceDataset(metadata=dataset.metadata, drivers=dataset.drivers, laps=(bad_lap,))


def test_dataset_rejects_duplicate_laps() -> None:
    dataset = create_demo_dataset()
    with pytest.raises(ValidationError, match="duplicate lap"):
        RaceDataset(
            metadata=dataset.metadata,
            drivers=dataset.drivers,
            laps=(dataset.laps[0], dataset.laps[0]),
        )

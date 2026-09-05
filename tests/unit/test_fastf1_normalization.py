from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import pytest

from f1_pitwall.ingestion.fastf1_source import FastF1Source


def test_fastf1_handles_nullable_metadata_and_accuracy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def get_driver(driver_id: str) -> dict[str, Any]:
        return {"Abbreviation": "NOR", "TeamColor": "NOTHEX", "FullName": pd.NA, "TeamName": pd.NA}

    def load(**kwargs: object) -> None:
        pass

    session = SimpleNamespace(
        drivers=["4"],
        get_driver=get_driver,
        load=load,
        event={"EventName": "Example", "Country": "Example", "Location": "Circuit"},
        laps=pd.DataFrame(
            [
                {
                    "Driver": "NOR",
                    "LapNumber": 1,
                    "Position": 1,
                    "LapTime": pd.Timedelta(seconds=90),
                    "Time": pd.Timedelta(seconds=90),
                    "IsAccurate": pd.NA,
                    "TrackStatus": pd.NA,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "f1_pitwall.ingestion.fastf1_source.fastf1.get_session", lambda *args: session
    )
    monkeypatch.setattr(
        "f1_pitwall.ingestion.fastf1_source.fastf1.Cache.enable_cache", lambda path: None
    )
    source = FastF1Source(tmp_path)
    dataset = source.fetch(2024, "Example", "S")
    assert dataset.drivers["NOR"].full_name == "NOR"
    assert dataset.drivers["NOR"].team_color == "777777"
    assert not dataset.laps[0].is_accurate
    assert dataset.metadata.session_id.endswith("-S")
    session.laps = pd.DataFrame([])
    with pytest.raises(ValueError, match="no usable"):
        source.fetch(2024, "Example")

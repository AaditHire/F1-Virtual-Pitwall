from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import pytest

from f1_pitwall.ingestion.fastf1_source import FastF1Source


@pytest.mark.parametrize(("year", "size"), [(2021, 20), (2023, 20), (2026, 22), (2030, 26)])
def test_fastf1_normalizes_arbitrary_session_grid_without_identity_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, year: int, size: int
) -> None:
    def get_driver(number: str) -> dict[str, Any]:
        return {
            "DriverId": f"stable-driver-{number}",
            "Abbreviation": f"A{number}",
            "TeamId": f"team-{int(number) // 2}",
            "TeamName": "Current Session Team",
            "FullName": f"Driver {number}",
            "GridPosition": int(number),
            "TeamColor": "123456",
        }

    session = SimpleNamespace(
        drivers=[str(i) for i in range(1, size + 1)],
        get_driver=get_driver,
        load=lambda **kwargs: None,
        total_laps=58,
        api_path="test",
        session_start_time=timedelta(hours=1),
        event={"EventName": "Contract Event", "Country": "Test", "Location": "Test"},
        laps=pd.DataFrame(
            [
                {
                    "Driver": f"A{i}",
                    "DriverNumber": str(i),
                    "LapNumber": 1,
                    "LapTime": pd.Timedelta("90s"),
                    "Time": pd.Timedelta("90s"),
                    "Position": i,
                }
                for i in range(1, size)
            ]
        ),
    )
    monkeypatch.setattr(
        "f1_pitwall.ingestion.fastf1_source.fastf1.get_session", lambda *args: session
    )
    monkeypatch.setattr(
        "f1_pitwall.ingestion.fastf1_source.fastf1.Cache.enable_cache", lambda path: None
    )
    monkeypatch.setattr(
        "f1_pitwall.ingestion.fastf1_source.fastf1_api.lap_count",
        lambda path: {
            "Time": [timedelta(0), timedelta(hours=2)],
            "TotalLaps": [session.total_laps, 2],
        },
    )
    source = FastF1Source(tmp_path)
    dataset = source.fetch(year, 1)
    assert len(dataset.drivers) == size
    assert len(dataset.laps) == size - 1
    assert dataset.metadata.total_laps == 58
    assert dataset.drivers["stable-driver-1"].team_id == "team-0"
    assert dataset.drivers["stable-driver-1"].grid_position == 1
    session.get_driver = lambda number: {
        **get_driver(number),
        "TeamId": "transferred-team",
        "TeamName": "New Session Team",
    }
    transferred = source.fetch(year, 2)
    assert (
        transferred.drivers["stable-driver-1"].driver_id
        == dataset.drivers["stable-driver-1"].driver_id
    )
    assert transferred.drivers["stable-driver-1"].team_id == "transferred-team"
    session.total_laps = None
    with pytest.raises(ValueError, match="Scheduled"):
        source.fetch(year, 1)


def test_qualifying_retains_nonclassified_entrants_and_rejects_future_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = []

    def get_driver(number: str) -> dict[str, Any]:
        return {
            "DriverId": f"stable-{number}",
            "Position": 1 if number == "1" else None,
            "Q1": pd.Timedelta("90s") if number == "1" else None,
        }

    session = SimpleNamespace(
        drivers=["1", "2"],
        get_driver=get_driver,
        load=lambda **kwargs: None,
        session_info={"EndDate": datetime(2026, 9, 5, 14, tzinfo=UTC), "GmtOffset": timedelta(0)},
        session_status=pd.DataFrame(
            [
                {"Status": "Finished", "Time": pd.Timedelta("1h")},
                {"Status": "Ends", "Time": pd.Timedelta("65min")},
            ]
        ),
    )

    def get_session(*args: object) -> SimpleNamespace:
        requested.append(args)
        return session

    monkeypatch.setattr("f1_pitwall.ingestion.fastf1_source.fastf1.get_session", get_session)
    monkeypatch.setattr(
        "f1_pitwall.ingestion.fastf1_source.fastf1.Cache.enable_cache", lambda path: None
    )
    source = FastF1Source(tmp_path)
    entries = source.qualifying_entrants(2026, 1, datetime(2026, 9, 5, 18, tzinfo=UTC))
    assert len(entries) == 2
    assert entries[1].confidence < entries[0].confidence
    assert requested == [(2026, 1, "Q")]
    with pytest.raises(ValueError, match="cutoff"):
        source.qualifying_entrants(2026, 1, datetime(2026, 9, 5, 13, tzinfo=UTC))
    session.session_status = pd.DataFrame([{"Status": "Started", "Time": pd.Timedelta("1h")}])
    with pytest.raises(ValueError, match="completion"):
        source.qualifying_entrants(2026, 1, datetime(2026, 9, 5, 18, tzinfo=UTC))


def test_nan_strings_do_not_collapse_unclassified_qualifying_drivers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = SimpleNamespace(
        drivers=["18", "3", "55"],
        get_driver=lambda number: {"DriverId": "nan", "TeamId": "nan", "Position": None},
        load=lambda **kwargs: None,
        session_info={"EndDate": datetime(2026, 9, 5, 14, tzinfo=UTC), "GmtOffset": timedelta(0)},
        session_status=pd.DataFrame(
            [
                {"Status": "Finished", "Time": pd.Timedelta("1h")},
                {"Status": "Ends", "Time": pd.Timedelta("65min")},
            ]
        ),
    )
    monkeypatch.setattr(
        "f1_pitwall.ingestion.fastf1_source.fastf1.get_session", lambda *args: session
    )
    monkeypatch.setattr(
        "f1_pitwall.ingestion.fastf1_source.fastf1.Cache.enable_cache", lambda path: None
    )
    entries = FastF1Source(tmp_path).qualifying_entrants(2026, 1, datetime(2026, 9, 6, tzinfo=UTC))
    assert len({entry.driver_id for entry in entries}) == 3
    assert all(entry.driver_id.startswith("2026-number-") for entry in entries)


def test_qualifying_connection_failure_is_a_provider_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from f1_pitwall.intelligence.provider import ProviderUnavailableError

    def failed(*args: object) -> None:
        raise OSError("network unavailable")

    monkeypatch.setattr("f1_pitwall.ingestion.fastf1_source.fastf1.get_session", failed)
    monkeypatch.setattr(
        "f1_pitwall.ingestion.fastf1_source.fastf1.Cache.enable_cache", lambda path: None
    )
    with pytest.raises(ProviderUnavailableError, match="unavailable"):
        FastF1Source(tmp_path).qualifying_entrants(2026, 1, datetime(2026, 9, 5, tzinfo=UTC))

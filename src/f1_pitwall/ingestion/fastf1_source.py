"""FastF1 adapter that emits the repository's normalized data contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fastf1  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from f1_pitwall.domain import Compound, DriverInfo, LapRecord, RaceDataset, RaceMetadata


def _milliseconds(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value.total_seconds() * 1000)


def _integer(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _compound(value: Any) -> Compound:
    normalized = str(value).upper()
    try:
        return Compound(normalized)
    except ValueError:
        return Compound.UNKNOWN


class FastF1Source:
    """Download a completed session and normalize only fields V1 understands."""

    def __init__(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(cache_dir))

    def fetch(self, year: int, event: str | int, session_name: str = "R") -> RaceDataset:
        """Fetch a session from FastF1 and return validated normalized records."""
        session = fastf1.get_session(year, event, session_name)
        session.load(telemetry=False, messages=False, weather=False)

        drivers: dict[str, DriverInfo] = {}
        for driver_id in session.drivers:
            result = session.get_driver(driver_id)
            abbreviation = str(result.get("Abbreviation") or driver_id)
            team_color = str(result.get("TeamColor") or "777777").lstrip("#")[:6]
            drivers[abbreviation] = DriverInfo(
                driver_id=abbreviation,
                full_name=str(result.get("FullName") or abbreviation),
                team_name=str(result.get("TeamName") or "Unknown"),
                team_color=team_color if len(team_color) == 6 else "777777",
            )

        records: list[LapRecord] = []
        for _, row in session.laps.iterrows():
            driver_id = str(row["Driver"])
            lap_number = _integer(row["LapNumber"])
            if lap_number is None or driver_id not in drivers:
                continue
            records.append(
                LapRecord(
                    driver_id=driver_id,
                    lap_number=lap_number,
                    source_lap=lap_number,
                    position=_integer(row.get("Position")),
                    lap_time_ms=_milliseconds(row.get("LapTime")),
                    elapsed_time_ms=_milliseconds(row.get("Time")),
                    compound=_compound(row.get("Compound")),
                    tyre_age_laps=_integer(row.get("TyreLife")),
                    stint=_integer(row.get("Stint")),
                    pit_in=not pd.isna(row.get("PitInTime")),
                    pit_out=not pd.isna(row.get("PitOutTime")),
                    track_status=str(row.get("TrackStatus") or ""),
                    is_accurate=bool(row.get("IsAccurate", False)),
                )
            )

        total_laps = max(record.lap_number for record in records)
        event_data = session.event
        event_slug = str(event_data.get("EventName", event)).upper().replace(" ", "-")
        metadata = RaceMetadata(
            session_id=f"{year}-{event_slug}-R",
            year=year,
            event_name=str(event_data.get("EventName") or event),
            country=str(event_data.get("Country") or "Unknown"),
            circuit=str(event_data.get("Location") or "Unknown"),
            total_laps=total_laps,
            source=f"FastF1 {fastf1.__version__}",
            data_version=f"fastf1-{fastf1.__version__}-{year}-{event}-R-v1",
        )
        return RaceDataset(
            metadata=metadata,
            drivers=drivers,
            laps=tuple(sorted(records, key=lambda lap: (lap.lap_number, lap.driver_id))),
        )

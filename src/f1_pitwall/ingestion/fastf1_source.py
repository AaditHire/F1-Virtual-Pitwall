"""FastF1 adapter that emits the repository's normalized data contract."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fastf1  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
from fastf1 import _api as fastf1_api

from f1_pitwall.domain import Compound, DriverInfo, LapRecord, RaceDataset, RaceMetadata
from f1_pitwall.intelligence.provider import ProviderUnavailableError
from f1_pitwall.simulation.models import Entrant


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


def _text(value: Any, fallback: str) -> str:
    if (
        value is None
        or pd.isna(value)
        or str(value).strip().casefold() in {"", "nan", "none", "<na>", "nat"}
    ):
        return fallback
    return str(value).strip()


class FastF1Source:
    """Download a completed session and normalize only fields V1 understands."""

    def __init__(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(cache_dir))

    def qualifying_entrants(self, year: int, event: int, as_of: datetime) -> tuple[Entrant, ...]:
        """Read the entire qualifying session roster without loading the target race."""
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        try:
            session = fastf1.get_session(year, event, "Q")
            session.load(telemetry=False, messages=False, weather=False)
        except Exception as error:
            raise ProviderUnavailableError("FastF1 qualifying session is unavailable.") from error
        ended = session.session_status.loc[
            session.session_status["Status"].isin(["Finished", "Finalised"]), "Time"
        ]
        if ended.empty or session.session_status.iloc[-1]["Status"] != "Ends":
            raise ValueError("Qualifying has no observed completion; predictions unavailable")
        # Without car telemetry FastF1 has no t0_date. Use a conservative upper bound:
        # scheduled session end plus the complete observed feed duration. This can delay
        # availability, but does not treat a partial Q1/Q2 result as final qualifying.
        info = session.session_info
        ended_at = pd.Timestamp(info["EndDate"] - info["GmtOffset"] + ended.max())
        ended_at = (
            ended_at.tz_localize("UTC") if ended_at.tzinfo is None else ended_at.tz_convert("UTC")
        )
        if ended_at.to_pydatetime() > as_of.astimezone(UTC):
            raise ValueError(
                "Qualifying results not yet beyond the conservative availability cutoff"
            )
        entrants = []
        for number in session.drivers:
            row = session.get_driver(number)
            times = [
                value
                for key in ("Q1", "Q2", "Q3")
                if (value := _milliseconds(row.get(key))) is not None and value > 0
            ]
            entrants.append(
                Entrant(
                    driver_id=_text(row.get("DriverId"), f"{year}-number-{number}"),
                    team_id=_text(row.get("TeamId"), _text(row.get("TeamName"), "unknown")),
                    grid_position=_integer(row.get("Position")) or 0,
                    base_pace_ms=min(times) * 1.04 if times else 90000,
                    pace_sigma_ms=1200 if times else 2000,
                    confidence=0.2 if times else 0.05,
                )
            )
        if not entrants:
            raise ValueError("Qualifying entrant list is unavailable")
        return tuple(entrants)

    def fetch(
        self,
        year: int,
        event: str | int,
        session_name: str = "R",
        scheduled_laps: int | None = None,
    ) -> RaceDataset:
        """Fetch a session from FastF1 and return validated normalized records."""
        session = fastf1.get_session(year, event, session_name)
        session.load(telemetry=False, messages=False, weather=False)

        drivers: dict[str, DriverInfo] = {}
        driver_numbers: dict[str, str] = {}
        abbreviations: dict[str, str] = {}
        for driver_id in session.drivers:
            result = session.get_driver(driver_id)
            abbreviation = _text(result.get("Abbreviation"), str(driver_id))
            team_color = _text(result.get("TeamColor"), "777777").lstrip("#")
            stable_id = _text(result.get("DriverId"), f"{year}-number-{driver_id}")
            driver_numbers[str(driver_id)] = stable_id
            abbreviations[abbreviation] = stable_id
            drivers[stable_id] = DriverInfo(
                driver_id=stable_id,
                abbreviation=abbreviation,
                team_id=_text(result.get("TeamId"), "") or None,
                grid_position=_integer(result.get("GridPosition")),
                full_name=_text(result.get("FullName"), abbreviation),
                team_name=_text(result.get("TeamName"), "Unknown"),
                team_color=team_color if re.fullmatch(r"[0-9A-Fa-f]{6}", team_color) else "777777",
            )

        records: list[LapRecord] = []
        for _, row in session.laps.iterrows():
            driver_id = driver_numbers.get(
                str(row.get("DriverNumber")), abbreviations.get(str(row.get("Driver")), "")
            )
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
                    track_status=_text(row.get("TrackStatus"), ""),
                    is_accurate=False
                    if pd.isna(row.get("IsAccurate"))
                    else bool(row.get("IsAccurate", False)),
                )
            )

        if not records:
            raise ValueError("The selected session has no usable completed lap records.")
        # FastF1.total_laps uses the last correction in the feed. Select pre-start
        # evidence instead so red-flag changes made later cannot change a replay.
        total_laps = scheduled_laps
        if total_laps is None:
            counts = fastf1_api.lap_count(session.api_path)
            start_time = session.session_start_time
            total_laps = next(
                (
                    int(count)
                    for observed_at, count in zip(counts["Time"], counts["TotalLaps"], strict=True)
                    if count and count > 0 and start_time is not None and observed_at <= start_time
                ),
                None,
            )
        if total_laps is None:
            raise ValueError("Scheduled total_laps unavailable; supply pre-race race distance.")
        event_data = session.event
        event_slug = str(event_data.get("EventName", event)).upper().replace(" ", "-")
        metadata = RaceMetadata(
            session_id=f"{year}-{event_slug}-{session_name}",
            year=year,
            event_name=str(event_data.get("EventName") or event),
            country=str(event_data.get("Country") or "Unknown"),
            circuit=str(event_data.get("Location") or "Unknown"),
            total_laps=total_laps,
            source=f"FastF1 {fastf1.__version__}",
            data_version=f"fastf1-{fastf1.__version__}-{year}-{event}-{session_name}-v2",
        )
        return RaceDataset(
            metadata=metadata,
            drivers=drivers,
            laps=tuple(sorted(records, key=lambda lap: (lap.lap_number, lap.driver_id))),
        )

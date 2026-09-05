"""Cutoff-safe reconstruction of immutable race snapshots."""

from __future__ import annotations

import hashlib
import json

from f1_pitwall.domain import (
    DataQualityWarning,
    DriverState,
    DriverStatus,
    LapRecord,
    RaceDataset,
    RaceSnapshot,
)


class CutoffViolationError(ValueError):
    """Raised when an observation crosses the requested replay cutoff."""


class ReplayBuilder:
    """Build race state using observations at or before one completed lap."""

    def __init__(self, dataset: RaceDataset) -> None:
        self._dataset = dataset

    def build(self, cutoff_lap: int) -> RaceSnapshot:
        """Return a deterministic snapshot and fail closed on future evidence."""
        metadata = self._dataset.metadata
        if not 1 <= cutoff_lap <= metadata.total_laps:
            raise ValueError(f"cutoff_lap must be between 1 and {metadata.total_laps}")

        visible = tuple(record for record in self._dataset.laps if record.lap_number <= cutoff_lap)
        if any(record.source_lap > cutoff_lap for record in visible):
            raise CutoffViolationError("visible data contains evidence after the cutoff")

        latest: dict[str, LapRecord] = {}
        for record in visible:
            current = latest.get(record.driver_id)
            if current is None or record.lap_number > current.lap_number:
                latest[record.driver_id] = record

        warnings: list[DataQualityWarning] = []
        ordered_records = sorted(
            latest.values(),
            key=lambda record: (
                record.position is None,
                record.position if record.position is not None else 999,
                record.driver_id,
            ),
        )
        leader = next((record for record in ordered_records if record.position == 1), None)
        ahead: LapRecord | None = None
        states: list[DriverState] = []

        for record in ordered_records:
            info = self._dataset.drivers[record.driver_id]
            gap = self._gap(record, leader)
            interval = self._gap(record, ahead)
            completed_delta = cutoff_lap - record.lap_number
            # Missing laps cannot establish a retirement without a status observation.
            status = DriverStatus.UNKNOWN if completed_delta > 0 else DriverStatus.RUNNING
            if completed_delta > 0:
                warnings.append(
                    DataQualityWarning(
                        code="STALE_TIMING",
                        message="Latest timing predates the cutoff; running status is unknown.",
                        driver_id=record.driver_id,
                    )
                )
            if record.position is None or record.elapsed_time_ms is None:
                warnings.append(
                    DataQualityWarning(
                        code="INCOMPLETE_TIMING",
                        message="Position or elapsed time is unavailable at this cutoff.",
                        driver_id=record.driver_id,
                    )
                )

            pit_stop_count = sum(
                1 for lap in visible if lap.driver_id == record.driver_id and lap.pit_in
            )
            states.append(
                DriverState(
                    driver_id=record.driver_id,
                    full_name=info.full_name,
                    team_name=info.team_name,
                    team_color=info.team_color,
                    status=status,
                    position=record.position,
                    completed_laps=record.lap_number,
                    laps_behind=completed_delta,
                    elapsed_time_ms=record.elapsed_time_ms,
                    gap_to_leader_ms=gap,
                    interval_ahead_ms=interval,
                    compound=record.compound,
                    tyre_age_laps=record.tyre_age_laps,
                    stint=record.stint,
                    pit_stop_count=pit_stop_count,
                    last_lap_time_ms=record.lap_time_ms,
                    max_source_lap=record.source_lap,
                )
            )
            ahead = record

        unseen = sorted(set(self._dataset.drivers) - set(latest))
        warnings.extend(
            DataQualityWarning(
                code="NO_VISIBLE_LAP",
                message="No completed lap is visible for this entrant.",
                driver_id=driver_id,
            )
            for driver_id in unseen
        )

        snapshot = RaceSnapshot(
            data_version=metadata.data_version,
            session_id=metadata.session_id,
            cutoff_lap=cutoff_lap,
            total_laps=metadata.total_laps,
            drivers=tuple(states),
            warnings=tuple(warnings),
        )
        canonical = json.dumps(
            snapshot.model_dump(mode="json", exclude={"snapshot_hash"}),
            sort_keys=True,
            separators=(",", ":"),
        )
        return snapshot.model_copy(
            update={"snapshot_hash": hashlib.sha256(canonical.encode()).hexdigest()}
        )

    @staticmethod
    def _gap(record: LapRecord, reference: LapRecord | None) -> int | None:
        if reference is None or record.driver_id == reference.driver_id:
            return 0 if reference is not None else None
        if record.lap_number != reference.lap_number:
            return None
        if record.elapsed_time_ms is None or reference.elapsed_time_ms is None:
            return None
        return max(0, record.elapsed_time_ms - reference.elapsed_time_ms)

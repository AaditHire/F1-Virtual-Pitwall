"""Canonical, immutable race and strategy contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    """Base model for deterministic value objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Compound(StrEnum):
    """Supported dry and wet tyre compounds."""

    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    INTERMEDIATE = "INTERMEDIATE"
    WET = "WET"
    UNKNOWN = "UNKNOWN"


class DriverStatus(StrEnum):
    """Observed driver status at a replay cutoff."""

    RUNNING = "RUNNING"
    RETIRED = "RETIRED"
    UNKNOWN = "UNKNOWN"


class StrategyAction(StrEnum):
    """Immediate strategy options evaluated in V1."""

    PIT_NEXT_LAP = "PIT_NEXT_LAP"
    STAY_OUT_ONE_LAP = "STAY_OUT_ONE_LAP"
    NO_RECOMMENDATION = "NO_RECOMMENDATION"


class TrafficRisk(StrEnum):
    """Coarse risk of rejoining near other cars."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class RaceMetadata(FrozenModel):
    """Pre-race facts and fixture provenance."""

    session_id: str = Field(min_length=1)
    year: int = Field(ge=1950)
    event_name: str = Field(min_length=1)
    country: str = Field(min_length=1)
    circuit: str = Field(min_length=1)
    total_laps: int = Field(gt=0)
    source: str = Field(min_length=1)
    data_version: str = Field(min_length=1)


class DriverInfo(FrozenModel):
    """Stable identity information for an entrant."""

    driver_id: str = Field(min_length=2, max_length=8)
    full_name: str = Field(min_length=1)
    team_name: str = Field(min_length=1)
    team_color: str = Field(pattern=r"^[0-9A-Fa-f]{6}$")


class LapRecord(FrozenModel):
    """Normalized observation for one driver's completed lap."""

    driver_id: str = Field(min_length=2, max_length=8)
    lap_number: int = Field(gt=0)
    source_lap: int = Field(gt=0)
    position: int | None = Field(default=None, gt=0)
    lap_time_ms: int | None = Field(default=None, gt=0)
    elapsed_time_ms: int | None = Field(default=None, gt=0)
    compound: Compound = Compound.UNKNOWN
    tyre_age_laps: int | None = Field(default=None, ge=0)
    stint: int | None = Field(default=None, gt=0)
    pit_in: bool = False
    pit_out: bool = False
    track_status: str = ""
    is_accurate: bool = False

    @model_validator(mode="after")
    def source_matches_observation(self) -> LapRecord:
        """A normalized lap cannot claim evidence from another lap."""
        if self.source_lap != self.lap_number:
            raise ValueError("source_lap must equal lap_number for raw lap records")
        return self


class RaceDataset(FrozenModel):
    """Versioned normalized race data used by replay."""

    metadata: RaceMetadata
    drivers: dict[str, DriverInfo]
    laps: tuple[LapRecord, ...]

    @model_validator(mode="after")
    def validate_dataset(self) -> RaceDataset:
        """Reject ambiguous records and unknown driver references."""
        seen: set[tuple[str, int]] = set()
        for lap in self.laps:
            if lap.driver_id not in self.drivers:
                raise ValueError(f"lap references unknown driver {lap.driver_id}")
            key = (lap.driver_id, lap.lap_number)
            if key in seen:
                raise ValueError(f"duplicate lap record {key}")
            seen.add(key)
        return self


class DataQualityWarning(FrozenModel):
    """Machine-readable limitation attached to an output."""

    code: str
    message: str
    driver_id: str | None = None


class DriverState(FrozenModel):
    """Observed state of one driver at a cutoff."""

    driver_id: str
    full_name: str
    team_name: str
    team_color: str
    status: DriverStatus
    position: int | None
    completed_laps: int
    laps_behind: int = Field(ge=0)
    elapsed_time_ms: int | None
    gap_to_leader_ms: int | None
    interval_ahead_ms: int | None
    compound: Compound
    tyre_age_laps: int | None
    stint: int | None
    pit_stop_count: int = Field(ge=0)
    last_lap_time_ms: int | None
    max_source_lap: int


class RaceSnapshot(FrozenModel):
    """Immutable race state at the end of a completed lap."""

    schema_version: str = "1.0"
    data_version: str
    session_id: str
    cutoff_lap: int = Field(gt=0)
    total_laps: int = Field(gt=0)
    drivers: tuple[DriverState, ...]
    warnings: tuple[DataQualityWarning, ...] = ()
    snapshot_hash: str = ""


class TyreTrend(FrozenModel):
    """Transparent linear tyre-pace trend."""

    driver_id: str
    compound: Compound
    stint: int | None
    sample_count: int = Field(ge=0)
    pace_ms: int | None
    degradation_ms_per_lap: float | None
    max_source_lap: int


class TrafficAnalysis(FrozenModel):
    """Predicted green-flag rejoin state."""

    driver_id: str
    assumed_pit_loss_ms: int = Field(gt=0)
    predicted_rejoin_position: int | None
    nearby_driver_ids: tuple[str, ...]
    risk: TrafficRisk
    max_source_lap: int


class StrategyOption(FrozenModel):
    """One modeled immediate action."""

    action: StrategyAction
    projected_time_ms: int | None
    delta_to_best_ms: int | None
    predicted_rejoin_position: int | None
    traffic_risk: TrafficRisk
    assumptions: tuple[str, ...]


class StrategyAssessment(FrozenModel):
    """Auditable comparison of immediate strategy choices."""

    session_id: str
    cutoff_lap: int
    driver_id: str
    preferred_action: StrategyAction
    confidence: float = Field(ge=0, le=1)
    options: tuple[StrategyOption, ...]
    evidence: tuple[str, ...]
    warnings: tuple[DataQualityWarning, ...]
    max_source_lap: int

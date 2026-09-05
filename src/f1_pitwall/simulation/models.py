"""Provider-independent inputs and auditable race simulation outputs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from f1_pitwall.domain.models import Compound, FrozenModel

MODEL_VERSION = "strategy-2.0"
SIMULATOR_VERSION = "monte-carlo-1.0"
DRY = frozenset({Compound.SOFT, Compound.MEDIUM, Compound.HARD})


class TyreSpec(FrozenModel):
    compound: Compound
    pace_offset_ms: float = 0
    degradation_ms_per_lap: float = Field(ge=0)
    max_life_laps: int = Field(gt=0)


class RaceRules(FrozenModel):
    """Explicit event assumptions; override for event regulations and allocations."""

    tyres: tuple[TyreSpec, ...] = (
        TyreSpec(
            compound=Compound.SOFT,
            pace_offset_ms=-600,
            degradation_ms_per_lap=110,
            max_life_laps=22,
        ),
        TyreSpec(compound=Compound.MEDIUM, degradation_ms_per_lap=65, max_life_laps=32),
        TyreSpec(
            compound=Compound.HARD, pace_offset_ms=450, degradation_ms_per_lap=40, max_life_laps=45
        ),
    )
    require_two_dry_compounds: bool = True
    mandatory_race_compounds: tuple[Compound, ...] = (Compound.MEDIUM, Compound.HARD)
    minimum_stops: int = Field(default=0, ge=0, le=6)
    max_stops: int = Field(default=3, ge=0, le=6)
    pit_loss_ms: float = Field(default=24000, gt=0)
    out_lap_penalty_ms: float = Field(default=1800, ge=0)
    overtaking_delta_ms: float = Field(default=500, ge=0)
    traffic_headway_ms: float = Field(default=700, ge=0)
    points: tuple[float, ...] = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)
    assumptions: tuple[str, ...] = (
        "Generic tyre life, compound offsets and green-flag pit loss; configure for the event.",
        "Full-distance points schedule; no fastest-lap or sprint bonuses.",
        "No weather transition, safety car, red flag or reliability forecast.",
    )

    @model_validator(mode="after")
    def validate_rules(self) -> RaceRules:
        compounds = [tyre.compound for tyre in self.tyres]
        if not compounds or len(set(compounds)) != len(compounds) or Compound.UNKNOWN in compounds:
            raise ValueError("tyres must contain unique known compounds")
        if self.minimum_stops > self.max_stops or any(point < 0 for point in self.points):
            raise ValueError("invalid stop limits or points")
        return self


class PaceEvidence(FrozenModel):
    """Each observation carries its availability time, not its download time alone."""

    driver_id: str | None = None
    team_id: str | None = None
    available_at: AwareDatetime
    observed_at: AwareDatetime
    source: Literal["practice", "historical", "team", "driver"]
    pace_ms: float = Field(gt=0)
    degradation_ms_per_lap: float | None = Field(default=None, ge=0)

    @field_validator("available_at", "observed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def ordered(self) -> PaceEvidence:
        if self.available_at < self.observed_at:
            raise ValueError("evidence cannot be available before it was observed")
        return self


class Entrant(FrozenModel):
    driver_id: str
    team_id: str = "unknown"
    grid_position: int = Field(ge=0)
    base_pace_ms: float = Field(gt=0)
    pace_sigma_ms: float = Field(default=650, ge=0)
    initial_gap_ms: float = Field(default=0, ge=0)
    current_compound: Compound = Compound.MEDIUM
    tyre_age_laps: int = Field(default=0, ge=0)
    used_compounds: tuple[Compound, ...] = ()
    available_compounds: tuple[Compound, ...] = ()
    compound_sets: dict[Compound, int] = Field(default_factory=dict)
    stops_completed: int = Field(default=0, ge=0)
    degradation_multiplier: float = Field(default=1, gt=0)
    confidence: float = Field(default=0.3, ge=0, le=1)


class SimulationState(FrozenModel):
    event_id: str
    total_laps: int = Field(gt=0, le=200)
    cutoff_lap: int = Field(default=0, ge=0)
    entrants: tuple[Entrant, ...] = Field(min_length=1, max_length=100)
    rules: RaceRules = Field(default_factory=RaceRules)
    excluded_driver_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    as_of: AwareDatetime | None = None
    race_start: AwareDatetime | None = None

    @field_validator("as_of", "race_start")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value else None

    @model_validator(mode="after")
    def validate_state(self) -> SimulationState:
        if self.cutoff_lap >= self.total_laps:
            raise ValueError("simulation requires laps remaining")
        ids = [entrant.driver_id for entrant in self.entrants]
        if len(set(ids)) != len(ids):
            raise ValueError("entrant IDs must be unique")
        if self.race_start is not None and (self.as_of is None or self.as_of >= self.race_start):
            raise ValueError("pre-race as_of must precede race_start")
        compounds = {tyre.compound for tyre in self.rules.tyres}
        for entrant in self.entrants:
            if entrant.current_compound not in compounds:
                raise ValueError("current compound must have a tyre model")
            if not set(entrant.available_compounds).issubset(compounds):
                raise ValueError("available compounds must have tyre models")
            if any(count < 0 for count in entrant.compound_sets.values()):
                raise ValueError("compound set counts must be non-negative")
        return self


class PreRaceRequest(FrozenModel):
    event_id: str
    race_start: AwareDatetime
    as_of: AwareDatetime
    total_laps: int = Field(gt=0, le=200)
    entrants: tuple[Entrant, ...] = Field(min_length=1, max_length=100)
    evidence: tuple[PaceEvidence, ...] = ()
    rules: RaceRules = Field(default_factory=RaceRules)
    grid_source: Literal["official", "provisional_qualifying", "user"] = "user"

    @field_validator("race_start", "as_of")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class PitStop(FrozenModel):
    after_lap: int = Field(ge=0)
    compound: Compound


class StrategyPlan(FrozenModel):
    name: str
    starting_compound: Compound
    stops: tuple[PitStop, ...] = ()
    projected_time_ms: float
    traffic_penalty_ms: float = 0


class DriverPrediction(FrozenModel):
    driver_id: str
    expected_finish: float
    median_finish: float
    expected_positions_gained: float
    expected_points: float
    points_probability: float
    top10_probability: float
    podium_probability: float
    win_probability: float
    realistic_best_result: int
    realistic_downside: int
    finish_distribution: dict[int, float]
    recommended_strategy: StrategyPlan
    alternative_strategy: StrategyPlan | None
    pit_window_start_lap: int | None = None
    pit_window_end_lap: int | None = None
    most_successful_strategy: str
    main_opportunity: str
    main_threat: str
    confidence: float
    utility: float


class SimulationResult(FrozenModel):
    event_id: str
    model_version: str = MODEL_VERSION
    simulator_version: str = SIMULATOR_VERSION
    simulations: int
    seed: int
    cutoff_lap: int
    predictions: tuple[DriverPrediction, ...]
    excluded_driver_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...]
    interpretation: str = (
        "Conditional model estimates, not calibrated probabilities. Upside is the 5th percentile "
        "of finish position; downside is the 95th. Each recommendation varies that driver's plan "
        "against fixed rival baseline plans; recommendations are not a joint equilibrium."
    )


class SimulationRequest(FrozenModel):
    state: SimulationState
    simulations: int = Field(default=100, ge=1, le=5000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)

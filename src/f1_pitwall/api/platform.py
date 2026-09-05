"""Typed full-grid strategy, simulations and provider-backed intelligence routes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from f1_pitwall.analytics.pits import PitLossEstimate, calculate_pit_loss
from f1_pitwall.application import PitWallService
from f1_pitwall.evaluations.historical import HistoricalReport, evaluate_historical
from f1_pitwall.intelligence.models import (
    Classification,
    Event,
    Grid,
    NewsFeed,
    Person,
    SessionTime,
    Standing,
    Team,
)
from f1_pitwall.intelligence.news import NewsProvider
from f1_pitwall.intelligence.service import IntelligenceService
from f1_pitwall.simulation.models import (
    DriverPrediction,
    PreRaceRequest,
    SimulationRequest,
    SimulationResult,
    SimulationState,
)
from f1_pitwall.simulation.race import simulate_race
from f1_pitwall.simulation.state import build_pre_race

router = APIRouter(prefix="/api/v1")


def _pitwall(request: Request) -> PitWallService:
    return request.app.state.service  # type: ignore[no-any-return]


def _intelligence(request: Request) -> IntelligenceService:
    return request.app.state.intelligence  # type: ignore[no-any-return]


def _news(request: Request) -> NewsProvider:
    return request.app.state.news  # type: ignore[no-any-return]


Pitwall = Annotated[PitWallService, Depends(_pitwall)]
Intelligence = Annotated[IntelligenceService, Depends(_intelligence)]
News = Annotated[NewsProvider, Depends(_news)]
Samples = Annotated[int, Query(ge=1, le=5000)]
Seed = Annotated[int, Query(ge=0, le=2**32 - 1)]


@router.get("/strategies/{lap}", tags=["strategy"])
def full_grid(
    lap: int, pitwall: Pitwall, simulations: Samples = 100, seed: Seed = 42
) -> SimulationResult:
    return pitwall.full_grid_strategy(lap, simulations, seed)


@router.get("/strategies/{lap}/{driver_id}", tags=["strategy"])
def driver_strategy(
    lap: int, driver_id: str, pitwall: Pitwall, simulations: Samples = 100, seed: Seed = 42
) -> DriverPrediction:
    identifier = pitwall.resolve_driver(driver_id)
    prediction = next(
        (
            driver
            for driver in pitwall.full_grid_strategy(lap, simulations, seed).predictions
            if driver.driver_id == identifier
        ),
        None,
    )
    if prediction is None:
        raise HTTPException(409, "Entrant is not active at this cutoff")
    return prediction


@router.get("/pit-loss/{lap}", tags=["strategy"])
def pit_loss(lap: int, pitwall: Pitwall) -> PitLossEstimate:
    return calculate_pit_loss(pitwall.dataset, lap)


@router.get("/evaluations/historical/{lap}", tags=["evaluation"])
def historical_evaluation(
    lap: int, pitwall: Pitwall, simulations: Samples = 100, seed: Seed = 42
) -> HistoricalReport:
    return evaluate_historical(pitwall.dataset, lap, simulations, seed)


@router.post("/simulation/pre-race-state", tags=["simulation"])
def pre_race_state(payload: PreRaceRequest) -> SimulationState:
    return build_pre_race(payload)


@router.post("/simulation/race", tags=["simulation"])
def race_simulation(payload: SimulationRequest) -> SimulationResult:
    return simulate_race(payload.state, payload.simulations, payload.seed)


@router.get("/seasons", tags=["intelligence"])
def seasons(service: Intelligence) -> tuple[int, ...]:
    return service.provider.seasons()


@router.get("/seasons/{year}/drivers", tags=["intelligence"])
def drivers(year: int, service: Intelligence) -> tuple[Person, ...]:
    return service.provider.drivers(year)


@router.get("/seasons/{year}/teams", tags=["intelligence"])
def teams(year: int, service: Intelligence) -> tuple[Team, ...]:
    return service.provider.teams(year)


@router.get("/seasons/{year}/calendar", tags=["intelligence"])
def calendar(year: int, service: Intelligence) -> tuple[Event, ...]:
    return service.provider.calendar(year)


@router.get("/events/current", tags=["intelligence"])
def current_event(service: Intelligence) -> Event | None:
    return service.current_event(datetime.now(UTC))


@router.get("/events/next", tags=["intelligence"])
def next_event(service: Intelligence) -> Event | None:
    return service.next_event(datetime.now(UTC))


@router.get("/sessions/next", tags=["intelligence"])
def next_session(service: Intelligence) -> SessionTime | None:
    return service.next_session(datetime.now(UTC))


@router.get("/events/{year}/{round_number}/qualifying", tags=["intelligence"])
def qualifying(year: int, round_number: int, service: Intelligence) -> tuple[Classification, ...]:
    return service.provider.classifications(year, round_number, "qualifying")


@router.get("/events/{year}/{round_number}/results", tags=["intelligence"])
def results(year: int, round_number: int, service: Intelligence) -> tuple[Classification, ...]:
    return service.provider.classifications(year, round_number)


@router.get("/events/{year}/{round_number}/sprint", tags=["intelligence"])
def sprint(year: int, round_number: int, service: Intelligence) -> tuple[Classification, ...]:
    return service.provider.classifications(year, round_number, "sprint")


@router.get("/events/{year}/{round_number}/grid", tags=["intelligence"])
def grid(year: int, round_number: int, service: Intelligence) -> Grid:
    return service.grid(year, round_number)


@router.get("/standings/drivers", tags=["intelligence"])
def driver_standings(service: Intelligence, year: int | None = None) -> tuple[Standing, ...]:
    return service.provider.standings(year if year is not None else datetime.now(UTC).year)


@router.get("/standings/constructors", tags=["intelligence"])
def constructor_standings(service: Intelligence, year: int | None = None) -> tuple[Standing, ...]:
    return service.provider.standings(year if year is not None else datetime.now(UTC).year, True)


@router.get("/news", tags=["intelligence"])
def news(provider: News, limit: Annotated[int, Query(ge=1, le=100)] = 30) -> NewsFeed:
    return provider.latest(limit)


@router.get("/predictions/next-race", tags=["simulation"])
def next_prediction(
    service: Intelligence,
    total_laps: Annotated[int, Query(ge=1, le=200)],
    simulations: Samples = 100,
    seed: Seed = 42,
) -> SimulationResult:
    request = service.next_race_request(datetime.now(UTC), total_laps)
    result = simulate_race(build_pre_race(request), simulations, seed)
    return result.model_copy(
        update={
            "warnings": (
                *result.warnings,
                "Pace is a low-confidence qualifying-time proxy with a 4% race-fuel adjustment.",
                "Race distance supplied by caller; verify scheduled laps and event regulations.",
            )
        }
    )

"""FastAPI application exposing cutoff-safe pit-wall analysis."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from f1_pitwall.agents.advisor import AgentUnavailableError, get_agent_advice
from f1_pitwall.api.platform import router as platform_router
from f1_pitwall.api.schemas import AgentAdviceRequest, RadioRequest
from f1_pitwall.application import PitWallService
from f1_pitwall.config import Settings, get_settings
from f1_pitwall.evaluations import run_evaluations
from f1_pitwall.ingestion.fastf1_source import FastF1Source
from f1_pitwall.intelligence.news import RssNewsProvider
from f1_pitwall.intelligence.provider import JolpicaProvider, ProviderUnavailableError
from f1_pitwall.intelligence.service import IntelligenceService
from f1_pitwall.logging import configure_logging
from f1_pitwall.radio import classify_radio
from f1_pitwall.rag import LocalKnowledgeIndex
from f1_pitwall.weather import OpenMeteoClient

logger = logging.getLogger(__name__)


def _service(request: Request) -> PitWallService:
    return request.app.state.service  # type: ignore[no-any-return]


def _knowledge(request: Request) -> LocalKnowledgeIndex:
    return request.app.state.knowledge  # type: ignore[no-any-return]


ServiceDep = Annotated[PitWallService, Depends(_service)]
KnowledgeDep = Annotated[LocalKnowledgeIndex, Depends(_knowledge)]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application instance for production or isolated tests."""
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.service = PitWallService.from_fixture(resolved.fixture_path)
        knowledge = LocalKnowledgeIndex(resolved.knowledge_db)
        knowledge.initialize()
        if resolved.knowledge_path.exists():
            knowledge.add_document(
                source=str(resolved.knowledge_path),
                title="Race Strategy Principles",
                content=resolved.knowledge_path.read_text(encoding="utf-8"),
            )
        app.state.knowledge = knowledge
        provider = JolpicaProvider(resolved.jolpica_url)
        news = RssNewsProvider(
            resolved.news_feeds,
            tags={
                "driver": {
                    info.full_name: info.driver_id
                    for info in app.state.service.dataset.drivers.values()
                },
                "team": {
                    info.team_name: info.team_id or info.team_name
                    for info in app.state.service.dataset.drivers.values()
                },
            },
        )
        cache_root = Path("/tmp/pitwall") if os.getenv("VERCEL") else Path("data/cache")
        app.state.intelligence = IntelligenceService(
            provider, FastF1Source(cache_root / "fastf1")
        )
        app.state.news = news
        try:
            yield
        finally:
            provider.close()
            news.close()

    app = FastAPI(
        title="F1 Virtual Pit Wall API",
        version="0.2.0",
        description="Cutoff-safe historical Formula 1 replay and strategy analysis.",
        lifespan=lifespan,
    )
    app.include_router(platform_router)

    @app.exception_handler(ProviderUnavailableError)
    async def provider_unavailable(
        request: Request, error: ProviderUnavailableError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"detail": str(error)}, headers={"Retry-After": "60"}
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))
        try:
            response = await call_next(request)
        except ValueError as error:
            logger.info("request rejected", extra={"request_id": request_id})
            response = JSONResponse(status_code=422, content={"detail": str(error)})
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/session", tags=["replay"])
    def session(pitwall: ServiceDep) -> dict[str, object]:
        dataset = pitwall.dataset
        return {
            "metadata": dataset.metadata,
            "drivers": list(dataset.drivers.values()),
        }

    @app.get("/api/v1/capabilities", tags=["operations"])
    def capabilities() -> dict[str, object]:
        return {
            "replay": "ready",
            "strategy": "ready",
            "tyres": "ready",
            "traffic": "ready",
            "radio": "ready",
            "knowledge": "ready",
            "weather": "ready",
            "agent": "ready" if os.getenv("OPENAI_API_KEY") else "requires_key",
        }

    @app.get("/api/v1/snapshot/{lap}", tags=["replay"])
    def snapshot(lap: int, pitwall: ServiceDep) -> object:
        return pitwall.snapshot(lap)

    @app.get("/api/v1/strategy/{driver_id}/{lap}", tags=["strategy"])
    def strategy(
        driver_id: str,
        lap: int,
        pitwall: ServiceDep,
    ) -> object:
        return pitwall.strategy(lap, driver_id)

    @app.get("/api/v1/lap-times/{lap}", tags=["replay"])
    def lap_times(
        lap: int,
        pitwall: ServiceDep,
        drivers: Annotated[str | None, Query()] = None,
    ) -> list[dict[str, object]]:
        selected = set(drivers.split(",")) if drivers else None
        return pitwall.lap_times(lap, selected)

    @app.get("/api/v1/tyres/{driver_id}/{lap}", tags=["strategy"])
    def tyre_trend(driver_id: str, lap: int, pitwall: ServiceDep) -> object:
        return pitwall.tyre_trend(lap, driver_id)

    @app.get("/api/v1/traffic/{driver_id}/{lap}", tags=["strategy"])
    def traffic(
        driver_id: str,
        lap: int,
        pitwall: ServiceDep,
        pit_loss_ms: Annotated[int, Query(ge=1_000, le=60_000)] = 24_000,
    ) -> object:
        return pitwall.traffic(lap, driver_id, pit_loss_ms)

    @app.get("/api/v1/trace/{driver_id}/{lap}", tags=["agents"])
    def trace(driver_id: str, lap: int, pitwall: ServiceDep) -> dict[str, object]:
        snapshot = pitwall.snapshot(lap)
        assessment = pitwall.strategy(lap, driver_id)
        return {
            "session_id": snapshot.session_id,
            "driver_id": driver_id.upper(),
            "cutoff_lap": lap,
            "snapshot_hash": snapshot.snapshot_hash,
            "max_source_lap": assessment.max_source_lap,
            "tool_sequence": ["get_race_state", "compare_strategy"],
            "evidence": assessment.evidence,
            "agent_status": "ready" if os.getenv("OPENAI_API_KEY") else "requires_key",
        }

    @app.get("/api/v1/evaluations", tags=["operations"])
    def evaluations(pitwall: ServiceDep) -> object:
        return run_evaluations(pitwall)

    @app.post("/api/v1/radio/classify", tags=["intelligence"])
    def radio(payload: RadioRequest) -> object:
        return classify_radio(payload.text)

    @app.get("/api/v1/knowledge/search", tags=["intelligence"])
    def search_knowledge(
        query: Annotated[str, Query(min_length=1, max_length=200)],
        index: KnowledgeDep,
        limit: Annotated[int, Query(ge=1, le=20)] = 5,
    ) -> object:
        return index.search(query, limit=limit)

    @app.get("/api/v1/weather", tags=["intelligence"])
    async def weather(
        latitude: Annotated[float, Query(ge=-90, le=90)],
        longitude: Annotated[float, Query(ge=-180, le=180)],
        day: date,
    ) -> object:
        try:
            return await OpenMeteoClient().fetch_day(
                latitude=latitude,
                longitude=longitude,
                day=day,
            )
        except Exception as error:
            logger.warning("weather provider unavailable", exc_info=error)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Historical weather provider is temporarily unavailable.",
            ) from error

    @app.post("/api/v1/agent/advice", tags=["agents"])
    async def agent_advice(
        payload: AgentAdviceRequest,
        pitwall: ServiceDep,
    ) -> object:
        try:
            return await get_agent_advice(
                pitwall,
                lap=payload.lap,
                driver_id=payload.driver_id,
                question=payload.question,
            )
        except AgentUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

    return app


app = create_app()

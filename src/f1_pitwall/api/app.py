"""FastAPI application exposing cutoff-safe pit-wall analysis."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from f1_pitwall.agents.advisor import AgentUnavailableError, get_agent_advice
from f1_pitwall.api.schemas import AgentAdviceRequest, RadioRequest
from f1_pitwall.application import PitWallService
from f1_pitwall.config import Settings, get_settings
from f1_pitwall.logging import configure_logging
from f1_pitwall.radio import classify_radio
from f1_pitwall.rag import LocalKnowledgeIndex

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
        app.state.knowledge = LocalKnowledgeIndex(resolved.knowledge_db)
        yield

    app = FastAPI(
        title="F1 Virtual Pit Wall API",
        version="0.1.0",
        description="Cutoff-safe historical Formula 1 replay and strategy analysis.",
        lifespan=lifespan,
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

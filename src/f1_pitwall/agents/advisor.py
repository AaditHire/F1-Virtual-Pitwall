"""Optional race-director agent layered over deterministic tools."""

from __future__ import annotations

import importlib
import os
from typing import Any

from f1_pitwall.application import PitWallService


class AgentUnavailableError(RuntimeError):
    """Raised when the opt-in hosted agent is not configured."""


async def get_agent_advice(
    service: PitWallService,
    *,
    lap: int,
    driver_id: str,
    question: str,
) -> dict[str, object]:
    """Ask one supervisor agent to explain deterministic analysis."""
    if not os.getenv("OPENAI_API_KEY"):
        raise AgentUnavailableError(
            "Agent advice is optional. Set OPENAI_API_KEY and install the 'agents' extra."
        )
    try:
        sdk: Any = importlib.import_module("agents")
    except ImportError as error:
        raise AgentUnavailableError(
            "Install the optional integration with: pip install -e '.[agents]'"
        ) from error

    service.snapshot(lap)

    def validate_tool_cutoff(cutoff_lap: int) -> None:
        if not 1 <= cutoff_lap <= lap:
            raise ValueError(f"Tool cutoff must be between 1 and the authorized lap {lap}.")

    @sdk.function_tool  # type: ignore[untyped-decorator]
    def get_race_state(cutoff_lap: int) -> str:
        """Return cutoff-safe race state as JSON."""
        validate_tool_cutoff(cutoff_lap)
        return service.snapshot(cutoff_lap).model_dump_json()

    @sdk.function_tool  # type: ignore[untyped-decorator]
    def compare_strategy(cutoff_lap: int, target_driver: str) -> str:
        """Return deterministic pit-versus-stay-out analysis as JSON."""
        validate_tool_cutoff(cutoff_lap)
        return service.strategy(cutoff_lap, target_driver).model_dump_json()

    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    agent = sdk.Agent(
        name="Race Director",
        model=model,
        instructions=(
            "You explain historical race strategy using only tool evidence at or before the "
            "requested cutoff. Never infer future events. State uncertainty and assumptions."
        ),
        tools=[get_race_state, compare_strategy],
    )
    prompt = f"At completed lap {lap}, advise {driver_id.upper()}. Question: {question}"
    result = await sdk.Runner.run(agent, prompt)
    return {
        "driver_id": driver_id.upper(),
        "cutoff_lap": lap,
        "model": model,
        "advice": str(result.final_output),
    }

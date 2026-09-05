import asyncio
import sys
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from f1_pitwall.agents.advisor import get_agent_advice
from f1_pitwall.application import PitWallService


def test_agent_tools_cannot_request_future_laps(
    service: PitWallService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def function_tool(function: Callable[..., str]) -> Callable[..., str]:
        return function

    async def run(agent: Any, prompt: str) -> SimpleNamespace:
        state, strategy = agent.tools
        assert '"cutoff_lap":12' in state(12)
        assert '"cutoff_lap":11' in strategy(11, "D001")
        with pytest.raises(ValueError, match="authorized lap 12"):
            state(13)
        with pytest.raises(ValueError, match="authorized lap 12"):
            strategy(30, "D001")
        return SimpleNamespace(final_output="Cutoff enforced")

    sdk = SimpleNamespace(
        function_tool=function_tool,
        Agent=SimpleNamespace,
        Runner=SimpleNamespace(run=run),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-placeholder")
    monkeypatch.setitem(sys.modules, "agents", sdk)
    result = asyncio.run(get_agent_advice(service, lap=12, driver_id="D001", question="Pit?"))
    assert result["advice"] == "Cutoff enforced"

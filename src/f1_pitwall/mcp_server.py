"""MCP server exposing deterministic pit-wall tools."""

from functools import lru_cache

from mcp.server.mcpserver import MCPServer

from f1_pitwall.application import PitWallService
from f1_pitwall.config import get_settings

mcp = MCPServer("F1 Virtual Pit Wall")


@lru_cache
def _service() -> PitWallService:
    return PitWallService.from_fixture(get_settings().fixture_path)


@mcp.tool()
def get_race_state(cutoff_lap: int) -> str:
    """Return reconstructed race state after a completed lap."""
    return _service().snapshot(cutoff_lap).model_dump_json(indent=2)


@mcp.tool()
def compare_strategy(cutoff_lap: int, driver_id: str) -> str:
    """Compare pitting next lap with staying out one more lap."""
    return _service().strategy(cutoff_lap, driver_id.upper()).model_dump_json(indent=2)


@mcp.tool()
def get_lap_times(
    cutoff_lap: int,
    driver_ids: list[str] | None = None,
) -> list[dict[str, object]]:
    """Return chart-ready lap times without observations after the cutoff."""
    selected = set(driver_ids) if driver_ids else None
    return _service().lap_times(cutoff_lap, selected)


def main() -> None:
    """Run the stdio MCP transport."""
    mcp.run()


if __name__ == "__main__":
    main()

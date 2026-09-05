"""Command-line interface for ingestion, replay, evaluation, and servers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NoReturn

import uvicorn

from f1_pitwall.application import PitWallService
from f1_pitwall.config import get_settings
from f1_pitwall.evaluations import run_evaluations
from f1_pitwall.ingestion import create_demo_dataset, write_fixture
from f1_pitwall.ingestion.fastf1_source import FastF1Source
from f1_pitwall.rag import LocalKnowledgeIndex


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pitwall", description="F1 Virtual Pit Wall")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Run the FastAPI server")
    commands.add_parser("mcp", help="Run the stdio MCP server")
    commands.add_parser("evaluate", help="Run deterministic evaluation cases")
    commands.add_parser("seed-demo", help="Write the synthetic demo fixture")

    replay = commands.add_parser("replay", help="Print a cutoff-safe race snapshot")
    replay.add_argument("--lap", type=int, required=True)
    strategy = commands.add_parser("strategy", help="Print deterministic strategy analysis")
    strategy.add_argument("--lap", type=int, required=True)
    strategy.add_argument("--driver", required=True)

    fetch = commands.add_parser("fetch", help="Download and normalize a completed FastF1 race")
    fetch.add_argument("--year", type=int, required=True)
    fetch.add_argument("--event", required=True)
    fetch.add_argument("--output", type=Path, required=True)
    fetch.add_argument("--total-laps", type=int, help="Explicit pre-race scheduled distance")
    index = commands.add_parser("index-knowledge", help="Index a local Markdown document")
    index.add_argument("path", type=Path)
    return parser


def _service() -> PitWallService:
    return PitWallService.from_fixture(get_settings().fixture_path)


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, default=str))


def main() -> NoReturn:
    """Dispatch one command and exit with a meaningful status."""
    args = _parser().parse_args()
    settings = get_settings()
    if args.command == "serve":
        uvicorn.run("f1_pitwall.api.app:app", host="127.0.0.1", port=8000, reload=False)
    elif args.command == "mcp":
        from f1_pitwall.mcp_server import main as run_mcp

        run_mcp()
    elif args.command == "seed-demo":
        write_fixture(create_demo_dataset(), settings.fixture_path)
        _print({"written": str(settings.fixture_path)})
    elif args.command == "replay":
        _print(_service().snapshot(args.lap).model_dump(mode="json"))
    elif args.command == "strategy":
        _print(_service().strategy(args.lap, args.driver).model_dump(mode="json"))
    elif args.command == "evaluate":
        results = run_evaluations(_service())
        _print([result.model_dump() for result in results])
        raise SystemExit(0 if all(result.passed for result in results) else 1)
    elif args.command == "fetch":
        dataset = FastF1Source(Path("data/cache/fastf1")).fetch(
            args.year, args.event, scheduled_laps=args.total_laps
        )
        write_fixture(dataset, args.output)
        _print({"written": str(args.output), "laps": len(dataset.laps)})
    elif args.command == "index-knowledge":
        index = LocalKnowledgeIndex(settings.knowledge_db)
        index.add_document(
            source=str(args.path),
            title=args.path.stem.replace("-", " ").title(),
            content=args.path.read_text(encoding="utf-8"),
        )
        _print({"indexed": str(args.path)})
    raise SystemExit(0)


if __name__ == "__main__":
    main()

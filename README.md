# F1 Virtual Pit Wall

An open-source, cutoff-safe Formula 1 race replay and strategy engineering platform. It
reconstructs a historical race after each completed lap and compares immediate decisions without
using later race data. Deterministic Python owns timing and strategy math; an optional OpenAI agent
can explain those tool outputs.

## Backend platform upgrade

The Python backend now includes dynamic full-grid replay, race-length strategy candidates,
position-dependent Monte Carlo recommendations, historical holdout evaluation, and a cached
Jolpica calendar/results/standings service. Configurable RSS/Atom feeds provide news metadata.
See [backend contracts, endpoints, assumptions and examples](docs/backend-platform.md).

The existing dashboard and optional agent/MCP/RAG integrations remain legacy interfaces. New
backend features are available through Python and the API; they have no new dashboard screens.

## What works now

- Synthetic zero-network demo plus FastF1 race ingestion
- Immutable lap-by-lap snapshots with evidence cutoffs and stable hashes
- Tyre degradation, pit rejoin traffic, and pit-versus-stay-out analysis
- FastAPI, CLI, and MCP interfaces over the same application service
- Local SQLite FTS5 knowledge retrieval and keyword radio intelligence
- Evaluation harness for cutoff safety, determinism, and explainability
- Responsive Next.js race-engineering dashboard

## Quick start

Python 3.12+ and Node.js 24+ are required.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
pitwall serve
```

In another terminal, run `cd frontend`, `npm ci`, and `npm run dev`. Open
<http://localhost:3000>; API docs are at <http://localhost:8000/docs>. The default synthetic fixture
is generated in memory, so the first run needs neither downloads nor credentials.

## Useful commands

```bash
pitwall replay --lap 12
pitwall strategy --lap 12 --driver D001
pitwall evaluate
python scripts/verify_platform.py  # optional live downloads and full-grid verification
pitwall index-knowledge knowledge/strategy-principles.md
pitwall fetch --year 2024 --event Bahrain --output data/samples/2024-bahrain.json
python -m f1_pitwall.mcp_server
docker compose up --build
```

FastF1 and Open-Meteo need no key. `OPENAI_API_KEY` is optional; without it only the natural-language
agent endpoint returns `503`, while replay, analytics, MCP, and dashboard features remain active.

## Quality checks

Run `python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`, and
`python -m mypy src tests`. In `frontend/`, run `npm test`, `npm run lint`, and `npm run build`.

## Interpreting the dashboard

The default session is synthetic and is labeled **Synthetic demo**. Set `PITWALL_FIXTURE_PATH`
to an ingested race file and restart the API to replay that session. The Next.js server forwards
requests through `PITWALL_API_URL` (default `http://127.0.0.1:8000`); this is a server environment
variable, not a browser URL.

The legacy `/api/v1/strategy/{driver}/{lap}` route compares two pit-stop timings over up to five remaining laps. It counts every projected
lap and returns no recommendation with fewer than three laps remaining. Both options include a
pit stop; the model does not yet optimize a complete race plan. Expand **Model assumptions** to
inspect its limitations. The evidence score is a sample-availability heuristic, not a calibrated
probability of success. Missing timing produces an unknown status rather than an inferred retirement.

Weather is a separate, full-day archive explorer with editable coordinates and date. It is not
fed into replay strategy. Agent tools enforce the requested lap in code; they cannot access later
laps even if a prompt requests them. General historical knowledge inside an LLM remains a separate
limitation when evaluating its explanations.

See [the architecture](docs/architecture.md), [build brief](docs/build-brief.md), and
[data-source policy](docs/data-sources.md). This project is licensed under MIT and is not affiliated
with Formula 1, the FIA, or any team.

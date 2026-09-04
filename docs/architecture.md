# System Architecture

F1 Virtual Pit Wall is a modular monolith with a Next.js client. This keeps deployment and local
development simple while preserving boundaries that can later become services.

```text
FastF1 / fixtures / Open-Meteo
             |
       normalization
             |
 immutable RaceDataset -> cutoff-safe ReplayBuilder
             |                    |
     tyre + traffic models -> StrategyAdvisor
             |
      PitWallService (single application facade)
       /       |        |         \
 FastAPI      CLI      MCP    optional Agent
    |
 Next.js dashboard
```

## Boundary Decisions

`domain/` contains frozen Pydantic contracts so bad data fails at ingestion rather than deep inside
analysis. `replay/` is the trust boundary: observations after the requested completed lap are not
visible. `analytics/` and `simulation/` are ordinary, deterministic Python because arithmetic,
sorting, and race invariants must be repeatable and testable.

`application/PitWallService` is the only facade used by HTTP, CLI, MCP, and agents. Sharing it avoids
four subtly different strategy implementations. SQLite FTS5 provides local RAG without operating a
vector database; a pgvector or Qdrant adapter becomes useful only after the knowledge corpus grows.

The optional OpenAI race-director agent explains deterministic tool outputs. It never owns timing
math and it is unavailable unless explicitly configured. This lets the entire engineering product
run without credentials while retaining a clean path to tracing, specialized agents, and hosted
model evaluations.

## Evolution Path

PostgreSQL should replace fixture storage when multiple races or users require concurrent queries.
Redis is deferred until measured workloads need shared caching or jobs. Agent specialization should
follow tool-level evaluation: add tyre, traffic, weather, and radio agents only when one supervisor
can no longer select and explain the deterministic tools reliably.

# End-to-End Build Brief

## Confirmed direction

F1 Virtual Pit Wall must replay historical races without future-data leakage, calculate
strategy deterministically, expose the calculations to APIs and tools, and provide an
operational dashboard. The first supported fixture is the 2024 Bahrain Grand Prix with
Lando Norris as the default analysis target.

The application must work without paid services. FastF1 supplies race timing; Open-Meteo
is the optional no-key weather source; SQLite FTS supplies local retrieval. OpenAI Agents
SDK integration is optional and remains disabled until `OPENAI_API_KEY` is configured.

## Runtime contract

- Input: session identifier, completed lap, and driver code.
- Output: immutable race snapshot plus a transparent two-option strategy assessment.
- Deterministic tools: race state, tyre trend, traffic/rejoin analysis, strategy comparison,
  radio tagging, and local knowledge search.
- State: versioned normalized fixture files; no hidden mutable race state.
- Safety boundary: every record carries `source_lap`; replay rejects future observations.
- UI: lap playback updates the field table, charts, and recommendation from the real API.
- Approval gates: none for read-only analysis. Data downloads are explicit CLI operations.

## Agent contract

One optional Race Director agent explains deterministic tool results. It may not invent
timing values or mutate race data. Missing API credentials return an explicit unavailable
status while the rest of the product continues to work.

## Deployment assumptions

The backend and frontend run locally or through Docker Compose. FastAPI exposes `/health`.
The dashboard targets the backend through `PITWALL_API_URL`. PostgreSQL, Redis, live timing,
and hosted vector storage remain future scaling choices rather than V1 requirements.


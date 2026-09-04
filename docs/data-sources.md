# Data Sources and Credentials

The application is free and local-first. A source adapter must keep its provenance, respect the
provider's terms, and normalize observations before replay. Raw caches and large downloads remain
untracked.

| Source | Cost / key | Intended use |
| --- | --- | --- |
| FastF1 | Free, no key | Historical timing, laps, stints, weather, and selected telemetry |
| Open-Meteo | Free, no key for non-commercial fair use | Historical and forecast weather |
| Jolpica F1 API | Free, no key | Schedules, results, standings, and Ergast-compatible records |
| Local Markdown + SQLite FTS5 | Free, offline | Licensed or original strategy knowledge for RAG |
| OpenAI API | Optional, usage-based key | Natural-language race-director explanations and tracing |

The deterministic engine must never depend on an LLM or paid service. It must also never ingest an
observation with `source_lap` later than the requested replay cutoff. Before publishing a dataset,
review its redistribution terms separately from the MIT license that covers this repository's code.

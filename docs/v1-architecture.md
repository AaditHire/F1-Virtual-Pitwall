# V1 Architecture Specification

> Historical decision record: this document defined the original deterministic-core milestone.
> The repository now includes the later interfaces described in `architecture.md`; the cutoff and
> domain invariants below remain authoritative.

**Status:** Accepted for implementation  
**Date:** 2026-09-01  
**Scope:** Offline, deterministic replay only

## 1. Objective

V1 proves that F1 Virtual Pit Wall can reconstruct a historical race at a lap boundary and compare two immediate strategy choices without reading later race events. It is deliberately a race-engineering core, not yet an AI application.

The initial fixture is the **2024 Bahrain Grand Prix**, with **Lando Norris (`NOR`)** as the focused strategy subject while state is reconstructed for the full field. Bahrain is useful because tyre management and two-stop strategy are central, while choosing a competitive midfield/front-running car creates meaningful traffic decisions. The race choice is reversible only if the ingestion audit finds material source-data gaps.

## 2. V1 Boundaries

V1 will:

- ingest a versioned, local fixture derived from FastF1-supported timing data;
- reconstruct all drivers at the end of every completed race lap;
- calculate basic tyre-age, recent-pace, gap, and likely rejoin-traffic features;
- compare `PIT_NEXT_LAP` with `STAY_OUT_ONE_LAP` over a short, documented horizon;
- emit a structured recommendation with evidence, assumptions, and confidence;
- run offline through tests or a small CLI.

V1 excludes LLMs, Agents SDK, MCP, RAG, radio, weather forecasts, live timing, databases, a web API, and a dashboard. These layers would add integration complexity before the numerical core is trustworthy.

## 3. Decision-Point Semantics

A decision point is `LapCutoff(session_id, completed_lap)`. Cutoff `N` means the race state immediately after lap `N` is complete:

- events attributable to laps `1..N` are visible;
- a pit stop made during lap `N` is visible;
- observations attributable to lap `N+1` or later are forbidden;
- pre-race facts, including the grid, scheduled distance, entrants, and circuit identity, are visible;
- missing information remains `unknown` and is never replaced with a future value.

V1 enforces **event-time isolation**. Historical timing feeds are post-processed, so V1 does not claim to reproduce the exact wall-clock availability of every observation during the live event. A later version may add `available_at` semantics for that stricter replay model.

Every derived value must retain the maximum source lap used to compute it. A query fails closed if that value exceeds the requested cutoff. Filtering only the final output is insufficient because leaked inputs could already have influenced a calculation.

## 4. Canonical Race-State Contract

`RaceSnapshot` is immutable and contains:

- `schema_version`, `data_version`, `session_id`, and `cutoff_lap`;
- scheduled race distance and current observed session status;
- one `DriverState` per entrant;
- data-quality warnings and a deterministic snapshot hash.

Each `DriverState` contains:

- stable driver and team identifiers;
- observed status, position, and completed laps;
- elapsed race time, gap to leader, and interval to the car ahead, with units;
- current stint number, compound, tyre age in laps, and observed pit-stop count;
- last valid lap time and identifiers for the source observations.

Unknown and unavailable values are nullable; they are not encoded as zero. Analytical features such as degradation slope and predicted pit loss are separate from canonical state so the factual snapshot remains independent of a particular model.

Required invariants:

1. No source observation has `source_lap > cutoff_lap`.
2. No driver has completed more laps than the cutoff.
3. Tyre age and pit-stop count are non-negative.
4. Active classified positions are unique within a snapshot.
5. Identical fixture, data version, and cutoff produce identical canonical JSON and hash.

## 5. Strategy Assessment Contract

For `NOR` at a requested cutoff, V1 returns:

- the two evaluated actions;
- estimated time delta over the configured short horizon;
- assumed green-flag pit loss;
- predicted rejoin position and nearby traffic;
- tyre and recent-pace evidence used;
- assumptions, data-quality warnings, and confidence;
- the preferred action, or `NO_RECOMMENDATION` when evidence is insufficient.

The initial model is intentionally transparent and rule/statistics based. It must expose its components rather than hide them behind a single score. Confidence represents input completeness and model applicability, not a calibrated probability of winning.

## 6. Acceptance Criteria

V1 is complete when:

1. The local fixture reconciles entrant count, race distance, and final classification against an authoritative reference.
2. Valid snapshots can be generated for every completed lap in the fixture.
3. Checkpoints at laps 10, 13, 16, 30, 33, and 36 pass manually recorded state assertions for `NOR` and surrounding cars.
4. Changing or deleting any fixture observation after cutoff `N` cannot change the snapshot or strategy assessment at `N`.
5. Repeated runs produce identical canonical JSON, snapshot hashes, and recommendations.
6. Invalid or incomplete data produces explicit warnings or `NO_RECOMMENDATION`, never fabricated values.
7. Unit tests cover cutoff enforcement and domain invariants; an offline integration test covers ingest-to-recommendation flow.
8. Tests require no network access and no secrets.

## 7. Deferred Decisions

PostgreSQL storage, live-feed availability timestamps, full-race simulation, probabilistic safety-car models, learned degradation models, agent orchestration, and final-position-based strategy scoring are deferred until this deterministic replay slice passes its acceptance criteria.

## 8. Evidence for Fixture Selection

The official race report describes the event as a predicted two-stop race with all 20 drivers starting on soft tyres, and the FIA classification records a 57-lap race. These references validate the fixture's suitability; implementation must still audit the actual ingestible fields before freezing the fixture.

- Formula 1 race report: <https://www.formula1.com/en/latest/article/verstappen-storms-to-victory-in-action-packed-season-opening-bahrain-gp.1rH6Yjju9FqISPgJy2NCCe>
- FIA race classification: <https://www.fia.com/events/fia-formula-one-world-championship/season-2024/bahrain-grand-prix/race-classification>

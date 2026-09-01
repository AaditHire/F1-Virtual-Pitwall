# Repository Guidelines

## Project Structure & Module Organization

The project uses a Python `src/` layout. Keep the root limited to project-wide configuration and documentation:

- `src/f1_pitwall/` contains domain, ingestion, replay, analytics, simulation, and application packages.
- `tests/unit/` contains isolated tests; `tests/integration/` covers offline flows across boundaries.
- `docs/` contains architecture decisions and data-contract guidance.
- `data/` may contain small redistributable samples; raw data and caches stay untracked.

Prefer small, feature-focused modules over a single large pit-wall service. Do not commit generated output, local caches, credentials, or large raw datasets.

## Build, Test, and Development Commands

Create a virtual environment, install `requirements-dev.lock`, then install the package with `python -m pip install --no-deps -e .`. Run `python -m pytest` for tests, `python -m ruff check .` for linting, `python -m ruff format --check .` for formatting, `python -m mypy src tests` for static typing, and `python -m build` to verify packaging.

Before submitting changes, use `git status` to confirm the intended files and `git diff --check` to catch whitespace errors.

## Coding Style & Naming Conventions

Use Ruff formatting with 100-character lines, four spaces, UTF-8 files, and final newlines. Mypy runs in strict mode. Use `snake_case` for modules and functions, `PascalCase` for classes, and `UPPER_CASE` for constants. Avoid unexplained abbreviations; established Formula 1 terms such as `DRS`, `ERS`, and `SC` are acceptable.

## Testing Guidelines

Pytest is the test framework and coverage must remain at least 90%. Name tests after observable behavior, such as `test_pit_window_opens_after_tyre_dropoff`. Keep tests deterministic and offline: store compact fixtures locally and mock external timing or weather feeds. Bug fixes require a regression test.

## Commit & Pull Request Guidelines

No Git history is available in this workspace, so use concise, imperative Conventional Commit messages, for example `feat: add tyre degradation model` or `fix: handle safety-car restart`. Pull requests should explain the problem and approach, list verification performed, link relevant issues, and include screenshots for UI changes. Call out schema, configuration, or data-source changes explicitly.

## Security & Configuration

Keep API keys and endpoints in environment variables. Commit a sanitized `.env.example`, never `.env`, and ensure logs and fixtures contain no private credentials or licensed telemetry data.

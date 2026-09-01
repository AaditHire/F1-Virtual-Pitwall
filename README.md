# F1 Virtual Pit Wall

F1 Virtual Pit Wall is a cutoff-safe historical Formula 1 replay and strategy-analysis
system. At a given completed lap, it will reconstruct only what was observable by that
point and compare race-strategy options without using future events.

The project is currently building its deterministic V1 foundation. LLM agents, MCP,
RAG, live timing, persistence, and the dashboard are intentionally deferred. See the
[V1 architecture specification](docs/v1-architecture.md) for the accepted scope and
correctness rules.

## Requirements

- Python 3.12 or newer
- No external services for the current milestone

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
```

The project uses standard Python packaging so contributors are not required to install
a global package manager. After changing dependencies in `pyproject.toml`, regenerate
the lock file with:

```powershell
python -m piptools compile --extra dev --output-file requirements-dev.lock pyproject.toml
```

## Quality checks

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy src tests
python -m pytest
python -m build
```

Run the formatter without `--check` to apply formatting:

```powershell
python -m ruff format .
```

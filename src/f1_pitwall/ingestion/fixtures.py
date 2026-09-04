"""Read and write normalized, versioned race fixtures."""

from pathlib import Path

from f1_pitwall.domain import RaceDataset


def load_fixture(path: Path) -> RaceDataset:
    """Load a normalized fixture and validate its complete contract."""
    return RaceDataset.model_validate_json(path.read_text(encoding="utf-8"))


def write_fixture(dataset: RaceDataset, path: Path) -> None:
    """Write stable JSON suitable for offline replay and review."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dataset.model_dump_json(indent=2) + "\n", encoding="utf-8")

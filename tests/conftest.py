from pathlib import Path

import pytest

from f1_pitwall.application import PitWallService
from f1_pitwall.ingestion import create_demo_dataset, write_fixture


@pytest.fixture
def service() -> PitWallService:
    return PitWallService(create_demo_dataset())


@pytest.fixture
def fixture_path(tmp_path: Path) -> Path:
    path = tmp_path / "race.json"
    write_fixture(create_demo_dataset(), path)
    return path
